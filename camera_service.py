import os
import time

import numpy as np


def build_camera_services(deps):
    cv2 = deps["cv2"]
    LOGGER = deps["LOGGER"]
    CAMERA_RETRY_SECONDS = deps["CAMERA_RETRY_SECONDS"]
    HISTORY_REFRESH_INTERVAL_SECONDS = deps["HISTORY_REFRESH_INTERVAL_SECONDS"]
    BEHAVIOR_DISPLAY_NAMES = deps["BEHAVIOR_DISPLAY_NAMES"]
    BehaviorTemporalAnalyzer = deps["BehaviorTemporalAnalyzer"]
    load_behavior_rules = deps["load_behavior_rules"]
    SessionFactory = deps["SessionFactory"]
    event_storage = deps["event_storage"]
    get_model = deps["get_model"]
    normalize_detections = deps["normalize_detections"]
    map_detections_to_behaviors = deps["map_detections_to_behaviors"]
    calculate_focus_score = deps["calculate_focus_score"]
    stats_lock = deps["stats_lock"]
    frame_lock = deps["frame_lock"]
    video_pipeline_lock = deps["video_pipeline_lock"]
    current_stats = deps["current_stats"]
    runtime_refs = deps["runtime_refs"]
    runtime_lock = deps["runtime_lock"]
    get_runtime_setting = deps["get_runtime_setting"]

    def camera_index():
        return int(get_runtime_setting("camera_index") or 0)

    def camera_width():
        return int(get_runtime_setting("camera_width") or 640)

    def camera_height():
        return int(get_runtime_setting("camera_height") or 480)

    def camera_backend():
        return deps["CAMERA_BACKEND"]

    def inference_every_n_frames():
        return max(1, int(get_runtime_setting("inference_every_n_frames") or 1))

    def inference_min_interval_seconds():
        return max(
            0.05, float(get_runtime_setting("inference_min_interval_seconds") or 0.05)
        )

    def yolo_imgsz():
        return max(64, int(get_runtime_setting("yolo_imgsz") or 416))

    def stream_fps():
        return max(1.0, float(get_runtime_setting("stream_fps") or 12.0))

    def _set_camera_status(status, message, last_error=None, available=False, placeholder_active=True):
        with runtime_lock:
            last_frame_at = runtime_refs.get("camera_status", {}).get("last_frame_at")
        payload = {
            "status": status,
            "available": available,
            "message": message,
            "last_error": last_error,
            "last_frame_at": last_frame_at,
            "placeholder_active": placeholder_active,
            "camera_index": camera_index(),
            "camera_backend": camera_backend(),
        }
        with runtime_lock:
            runtime_refs["camera_status"] = payload
        with stats_lock:
            current_stats["camera_status"] = dict(payload)

    def _build_placeholder_frame(message=None):
        width = max(640, camera_width())
        height = max(360, camera_height())
        canvas = np.full((height, width, 3), (28, 34, 45), dtype=np.uint8)

        accent_top = max(24, height // 12)
        canvas[:accent_top, :, :] = (28, 93, 106)
        cv2.putText(
            canvas,
            "SMART CLASSROOM",
            (20, min(height - 20, 36)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (240, 246, 250),
            2,
        )

        lines = [
            "Camera unavailable",
            "System switched to placeholder frame.",
            "Check CAMERA_INDEX, CAMERA_BACKEND, or device connection.",
        ]
        start_y = height // 3
        for index, line in enumerate(lines):
            font_scale = 0.9 if index == 0 else 0.58
            color = (245, 248, 250) if index == 0 else (209, 219, 226)
            cv2.putText(
                canvas,
                line,
                (24, start_y + index * 42),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                color,
                2,
            )

        badge_text = "Placeholder Frame"
        badge_size, _ = cv2.getTextSize(
            badge_text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1
        )
        badge_x = width - badge_size[0] - 28
        badge_y = height - 22
        cv2.rectangle(
            canvas,
            (badge_x - 10, badge_y - 22),
            (width - 18, badge_y + 8),
            (47, 107, 102),
            -1,
        )
        cv2.putText(
            canvas,
            badge_text,
            (badge_x, badge_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (245, 248, 250),
            1,
        )
        return canvas

    def _resolve_camera_backends():
        backend_map = {"default": None}
        if hasattr(cv2, "CAP_DSHOW"):
            backend_map["dshow"] = cv2.CAP_DSHOW
        if hasattr(cv2, "CAP_MSMF"):
            backend_map["msmf"] = cv2.CAP_MSMF
        if hasattr(cv2, "CAP_ANY"):
            backend_map["any"] = cv2.CAP_ANY

        preferred_backend = camera_backend()
        if preferred_backend in backend_map and preferred_backend != "auto":
            return [backend_map[preferred_backend]]

        backends = [None]
        for backend_name in ("dshow", "msmf", "any"):
            backend = backend_map.get(backend_name)
            if backend is not None and backend not in backends:
                backends.append(backend)
        return backends

    def open_camera():
        candidate_indexes = [camera_index()]
        for fallback_index in (0, 1, 2):
            if fallback_index not in candidate_indexes:
                candidate_indexes.append(fallback_index)

        _set_camera_status(
            "starting",
            "正在初始化实时摄像头。",
            available=False,
            placeholder_active=True,
        )

        for backend in _resolve_camera_backends():
            for candidate_index in candidate_indexes:
                if backend is None:
                    cap = cv2.VideoCapture(candidate_index)
                    backend_name = "default"
                else:
                    cap = cv2.VideoCapture(candidate_index, backend)
                    backend_name = str(backend)

                if not cap.isOpened():
                    cap.release()
                    continue

                cap.set(cv2.CAP_PROP_FRAME_WIDTH, camera_width())
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, camera_height())
                ok, frame = cap.read()
                if ok and frame is not None:
                    LOGGER.info(
                        "Using camera index=%s backend=%s frame_shape=%s",
                        candidate_index,
                        backend_name,
                        frame.shape,
                    )
                    _set_camera_status(
                        "ok",
                        "实时摄像头已连接，正在输出监测画面。",
                        available=True,
                        placeholder_active=False,
                    )
                    return cap

                cap.release()

        raise RuntimeError(
            "Unable to open a working camera stream. Try setting CAMERA_INDEX or CAMERA_BACKEND."
        )

    def refresh_public_history_cache():
        latest_snapshot = event_storage.get_latest_snapshot(only_public=True)
        with stats_lock:
            current_stats["latest_snapshot"] = latest_snapshot
        runtime_refs["last_public_history_refresh_at"] = time.time()

    def refresh_public_history_cache_if_needed(force=False):
        if force or (
            time.time() - runtime_refs["last_public_history_refresh_at"]
        ) >= HISTORY_REFRESH_INTERVAL_SECONDS:
            refresh_public_history_cache()

    def reset_runtime_stats():
        runtime_refs["temporal_analyzer"] = BehaviorTemporalAnalyzer(
            load_behavior_rules(SessionFactory)
        )
        with stats_lock:
            current_stats["stable_counts"] = {key: 0 for key in BEHAVIOR_DISPLAY_NAMES}
            current_stats["durations"] = {key: 0.0 for key in BEHAVIOR_DISPLAY_NAMES}
            current_stats["alerts"] = []
            current_stats["behavior_details"] = {}
            current_stats["frame_behaviors"] = {}
            current_stats["detections"] = []
            current_stats["focus_score"] = calculate_focus_score(
                current_stats["stable_counts"]
            )
            current_stats["last_updated"] = None
            current_stats["camera_status"] = dict(runtime_refs["camera_status"])
        refresh_public_history_cache_if_needed(force=True)

    def save_alert_snapshot(frame, alert_payload, user_id=None, job_id=None):
        filename_prefix = job_id[:8] if job_id else None
        filename = event_storage.build_snapshot_filename(
            alert_payload["behavior_key"],
            alert_payload["timestamp"],
            prefix=filename_prefix,
        )
        snapshot_path = os.path.join(event_storage.snapshot_dir, filename)

        snapshot = frame.copy()
        cv2.putText(
            snapshot,
            "Alert: {}".format(alert_payload["behavior_name"]),
            (18, 32),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 255),
            2,
        )
        cv2.putText(
            snapshot,
            "Duration: {:.1f}s".format(alert_payload["duration_seconds"]),
            (18, 64),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 255),
            2,
        )
        cv2.imwrite(snapshot_path, snapshot)

        return event_storage.record_event(
            behavior_key=alert_payload["behavior_key"],
            behavior_name=alert_payload["behavior_name"],
            duration_seconds=alert_payload["duration_seconds"],
            timestamp=alert_payload["timestamp"],
            count=alert_payload["count"],
            snapshot_path="/snapshots/{}".format(filename),
            user_id=user_id,
            job_id=job_id,
        )

    def annotate_frame(frame):
        annotated_frame = frame.copy()
        with stats_lock:
            stable_counts = dict(current_stats["stable_counts"])
            alert_count = len(current_stats["alerts"])
            latest_snapshot = current_stats["latest_snapshot"]
            detections = list(current_stats["detections"])
            camera_status = dict(current_stats["camera_status"])

        for detection in detections:
            bbox = detection.get("bbox") or []
            if len(bbox) != 4:
                continue
            x1, y1, x2, y2 = [int(value) for value in bbox]
            confidence = float(detection.get("confidence", 0.0))
            label = detection.get("class_name") or detection.get("behavior_name") or "obj"
            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 220, 255), 2)
            cv2.putText(
                annotated_frame,
                "{} {:.2f}".format(label, confidence),
                (x1, max(20, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 220, 255),
                2,
            )

        summary_text = "LowHead:{}  Sleep:{}  Hand:{}  Talk:{}".format(
            stable_counts.get("low_head", 0),
            stable_counts.get("sleep", 0),
            stable_counts.get("hand_raise", 0),
            stable_counts.get("turn_talk", 0),
        )
        cv2.putText(
            annotated_frame,
            summary_text,
            (16, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 255, 0),
            2,
        )
        if alert_count:
            cv2.putText(
                annotated_frame,
                "Alert Active: {}".format(alert_count),
                (16, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 255),
                2,
            )
        if latest_snapshot:
            cv2.putText(
                annotated_frame,
                "Last Snapshot: {}".format(latest_snapshot["behavior_name"]),
                (16, 90),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 0),
                2,
            )
        if not camera_status.get("available"):
            cv2.putText(
                annotated_frame,
                "Camera unavailable",
                (16, 120),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                2,
            )
        return annotated_frame

    def update_behavior_stats(results, timestamp, snapshot_frame):
        model = get_model()
        detections = normalize_detections(results[0], model.names, timestamp)
        frame_behaviors = map_detections_to_behaviors(detections)

        def handle_alert(alert_payload):
            save_alert_snapshot(snapshot_frame, alert_payload)

        temporal_state = runtime_refs["temporal_analyzer"].update(
            frame_behaviors,
            timestamp,
            alert_callback=handle_alert,
        )
        refresh_public_history_cache_if_needed(force=bool(temporal_state["triggered_alerts"]))
        focus_score = calculate_focus_score(temporal_state["stable_counts"])

        with stats_lock:
            current_stats["stable_counts"] = temporal_state["stable_counts"]
            current_stats["durations"] = temporal_state["durations"]
            current_stats["alerts"] = temporal_state["active_alerts"]
            current_stats["behavior_details"] = temporal_state["behavior_details"]
            current_stats["frame_behaviors"] = {
                key: value.to_dict() for key, value in frame_behaviors.items()
            }
            current_stats["detections"] = [detection.to_dict() for detection in detections]
            current_stats["focus_score"] = focus_score
            current_stats["last_updated"] = timestamp

    def capture_frames_loop():
        while True:
            try:
                cap = open_camera()
            except Exception as exc:
                LOGGER.exception("Failed to open camera")
                with frame_lock:
                    runtime_refs["latest_camera_frame"] = None
                _set_camera_status(
                    "degraded",
                    "未检测到可用摄像头，已切换到占位画面。",
                    last_error=str(exc),
                    available=False,
                    placeholder_active=True,
                )
                time.sleep(CAMERA_RETRY_SECONDS)
                continue

            try:
                last_capture_at = 0.0
                while True:
                    loop_started_at = time.perf_counter()
                    success, frame = cap.read()
                    if not success:
                        LOGGER.warning("Camera read failed, retrying camera open")
                        _set_camera_status(
                            "degraded",
                            "摄像头读取中断，系统正在尝试重新连接。",
                            last_error="camera_read_failed",
                            available=False,
                            placeholder_active=True,
                        )
                        break
                    with frame_lock:
                        runtime_refs["latest_camera_frame"] = frame.copy()
                    now_ts = time.time()
                    with runtime_lock:
                        status_payload = dict(runtime_refs.get("camera_status", {}))
                        status_payload["last_frame_at"] = now_ts
                        runtime_refs["camera_status"] = status_payload
                        reconnect_requested = bool(runtime_refs.get("camera_reconnect_requested"))
                        if reconnect_requested:
                            runtime_refs["camera_reconnect_requested"] = False
                    with stats_lock:
                        current_stats["camera_status"] = dict(status_payload)
                    if reconnect_requested:
                        break

                    target_interval = 1.0 / max(1.0, stream_fps())
                    now_capture_at = time.perf_counter()
                    if last_capture_at:
                        since_last = now_capture_at - last_capture_at
                        if since_last < target_interval:
                            time.sleep(max(0.0, target_interval - since_last))
                    else:
                        elapsed = time.perf_counter() - loop_started_at
                        if elapsed < target_interval:
                            time.sleep(max(0.0, target_interval - elapsed))
                    last_capture_at = time.perf_counter()
            finally:
                cap.release()
                time.sleep(CAMERA_RETRY_SECONDS)

    def inference_loop():
        frame_index = 0
        last_inference_at = 0.0
        last_seen_frame_at = 0.0

        while True:
            with runtime_lock:
                frame_at = (runtime_refs.get("camera_status", {}) or {}).get("last_frame_at") or 0.0
            if not frame_at or frame_at == last_seen_frame_at:
                time.sleep(0.02)
                continue

            with frame_lock:
                frame = (
                    None
                    if runtime_refs["latest_camera_frame"] is None
                    else runtime_refs["latest_camera_frame"].copy()
                )

            if frame is None:
                time.sleep(0.05)
                continue

            last_seen_frame_at = frame_at

            should_run_inference = (
                frame_index == 0 or frame_index % inference_every_n_frames() == 0
            )
            enough_time_elapsed = (
                time.time() - last_inference_at
            ) >= inference_min_interval_seconds()

            if should_run_inference and enough_time_elapsed:
                timestamp = time.time()
                try:
                    model = get_model()
                    results = model.predict(
                        frame,
                        conf=0.35,
                        iou=0.45,
                        imgsz=yolo_imgsz(),
                        verbose=False,
                    )
                    plotted = results[0].plot()
                    update_behavior_stats(results, timestamp, plotted)
                    last_inference_at = time.time()
                except Exception:
                    LOGGER.exception("Inference failed on camera frame")

            frame_index += 1
            time.sleep(0.005)

    def ensure_video_pipeline_started():
        with runtime_lock:
            if runtime_refs.get("video_pipeline_started"):
                return

        with video_pipeline_lock:
            with runtime_lock:
                if runtime_refs.get("video_pipeline_started"):
                    return

            deps["threading"].Thread(
                target=capture_frames_loop,
                name="camera-capture",
                daemon=True,
            ).start()
            deps["threading"].Thread(
                target=inference_loop,
                name="camera-inference",
                daemon=True,
            ).start()
            with runtime_lock:
                runtime_refs["video_pipeline_started"] = True

    def get_display_frame():
        with frame_lock:
            frame = (
                None
                if runtime_refs["latest_camera_frame"] is None
                else runtime_refs["latest_camera_frame"].copy()
            )

        if frame is None:
            with runtime_lock:
                message = (runtime_refs.get("camera_status", {}) or {}).get("message")
            return _build_placeholder_frame(message)
        return annotate_frame(frame)

    def generate_frames():
        ensure_video_pipeline_started()
        while True:
            frame_interval = 1.0 / stream_fps()
            frame = get_display_frame()
            ret, buffer = cv2.imencode(".jpg", frame)
            if not ret:
                time.sleep(frame_interval)
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
            )
            time.sleep(frame_interval)

    return {
        "_resolve_camera_backends": _resolve_camera_backends,
        "open_camera": open_camera,
        "refresh_public_history_cache": refresh_public_history_cache,
        "refresh_public_history_cache_if_needed": refresh_public_history_cache_if_needed,
        "reset_runtime_stats": reset_runtime_stats,
        "save_alert_snapshot": save_alert_snapshot,
        "annotate_frame": annotate_frame,
        "update_behavior_stats": update_behavior_stats,
        "capture_frames_loop": capture_frames_loop,
        "inference_loop": inference_loop,
        "ensure_video_pipeline_started": ensure_video_pipeline_started,
        "get_display_frame": get_display_frame,
        "generate_frames": generate_frames,
    }
