import json
import logging
import os
import time
from datetime import datetime
from typing import Optional

import cv2
from sqlalchemy import or_
from ultralytics import YOLO

from analysis_service import create_upload_analysis_service
from app_config import build_runtime_summary, load_runtime_config
from app_core.context import create_app_context
from app_core.detection_models import RoboflowHostedModel
from app_core.inference_runtime import inference_device_label
from app_core.job_executor import UploadAnalysisTask
from app_core.repositories import build_repository_helpers
from behavior_core import (
    BEHAVIOR_DISPLAY_NAMES,
    BEHAVIOR_RULES,
    BehaviorTemporalAnalyzer,
    map_detections_to_behaviors,
    normalize_detections,
)
from config_service import build_config_services
from database import (
    AlertEvent,
    AnalysisReport,
    SystemConfig,
    User,
    VideoAnalysisJob,
    load_behavior_rules,
    session_scope,
)
from experiment_data import EXPERIMENT_OVERVIEW
from focus_score import calculate_focus_score as _shared_calculate_focus_score
from report_service import build_report_services

LOGGER = logging.getLogger(__name__)

_WORKER_SERVICE = None


def _json_dumps(payload) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _json_loads(value: Optional[str], fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _format_dt(value: Optional[datetime]) -> str:
    if not value:
        return "--"
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _format_timestamp(value: Optional[float]) -> str:
    if not value:
        return "--"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(value))


def _build_initial_camera_status():
    runtime_config = load_runtime_config()
    return {
        "status": "idle",
        "available": False,
        "message": "Camera pipeline is not started in worker mode.",
        "last_error": None,
        "last_frame_at": None,
        "placeholder_active": True,
        "camera_index": runtime_config.camera_index,
        "camera_backend": runtime_config.camera_backend,
    }


def _build_initial_model_state():
    runtime_config = load_runtime_config()
    if runtime_config.inference_provider == "roboflow":
        model_ready = runtime_config.roboflow_api_key_present
        return {
            "status": "ready" if model_ready else "warning",
            "loaded": False,
            "message": (
                "Roboflow hosted classroom model is configured."
                if model_ready
                else "Roboflow provider selected but ROBOFLOW_API_KEY is missing."
            ),
            "path": runtime_config.roboflow_model_id,
            "provider": runtime_config.inference_provider,
            "device": "hosted",
            "last_error": None,
        }

    model_exists = os.path.exists(runtime_config.model_path)
    return {
        "status": "ready" if model_exists else "warning",
        "loaded": False,
        "message": "Model file detected." if model_exists else "Model file is missing.",
        "path": runtime_config.model_path,
        "provider": runtime_config.inference_provider,
        "device": inference_device_label(),
        "last_error": None,
    }


def _calculate_focus_score(stable_counts: dict) -> dict:
    return _shared_calculate_focus_score(stable_counts)


def _build_worker_service():
    runtime_config = load_runtime_config()
    app_context = create_app_context(
        runtime_config=runtime_config,
        logger=LOGGER,
        initial_camera_status_factory=_build_initial_camera_status,
        initial_model_state_factory=_build_initial_model_state,
    )

    def get_model():
        if app_context.model is not None:
            return app_context.model
        with app_context.model_lock:
            if app_context.model is not None:
                return app_context.model
            if runtime_config.inference_provider == "roboflow":
                app_context.model = RoboflowHostedModel.from_env()
            else:
                app_context.model = YOLO(runtime_config.model_path, task="detect")
            return app_context.model

    def save_alert_snapshot(frame, alert_payload, user_id=None, job_id=None):
        filename_prefix = job_id[:8] if job_id else None
        filename = app_context.event_storage.build_snapshot_filename(
            alert_payload["behavior_key"],
            alert_payload["timestamp"],
            prefix=filename_prefix,
        )
        snapshot_path = os.path.join(app_context.event_storage.snapshot_dir, filename)
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
        return app_context.event_storage.record_event(
            behavior_key=alert_payload["behavior_key"],
            behavior_name=alert_payload["behavior_name"],
            duration_seconds=alert_payload["duration_seconds"],
            timestamp=alert_payload["timestamp"],
            count=alert_payload["count"],
            snapshot_path="/snapshots/{}".format(filename),
            user_id=user_id,
            job_id=job_id,
        )

    deps = {
        "AlertEvent": AlertEvent,
        "ALLOWED_IMAGE_EXTENSIONS": set(runtime_config.allowed_image_extensions),
        "ALLOWED_VIDEO_EXTENSIONS": set(runtime_config.allowed_video_extensions),
        "AnalysisReport": AnalysisReport,
        "BEHAVIOR_DISPLAY_NAMES": BEHAVIOR_DISPLAY_NAMES,
        "BEHAVIOR_RULES": BEHAVIOR_RULES,
        "BehaviorTemporalAnalyzer": BehaviorTemporalAnalyzer,
        "CAMERA_HEIGHT": runtime_config.camera_height,
        "CAMERA_INDEX": runtime_config.camera_index,
        "CAMERA_WIDTH": runtime_config.camera_width,
        "EXPERIMENT_OVERVIEW": EXPERIMENT_OVERVIEW,
        "INFERENCE_EVERY_N_FRAMES": runtime_config.inference_every_n_frames,
        "INFERENCE_MIN_INTERVAL_SECONDS": runtime_config.inference_min_interval_seconds,
        "LOGGER": LOGGER,
        "MAX_UPLOAD_BYTES": runtime_config.max_upload_bytes,
        "MODEL_PATH": runtime_config.model_path,
        "ROLE_ADMIN": "admin",
        "ROLE_TEACHER": "teacher",
        "STREAM_FPS": runtime_config.stream_fps,
        "SessionFactory": app_context.session_factory,
        "SystemConfig": SystemConfig,
        "User": User,
        "UPLOAD_DIR": runtime_config.upload_dir,
        "VIDEO_ANALYSIS_FRAME_STRIDE": runtime_config.video_analysis_frame_stride,
        "VideoAnalysisJob": VideoAnalysisJob,
        "YOLO_IMGSZ": runtime_config.yolo_imgsz,
        "YOLO_CONFIDENCE": runtime_config.yolo_confidence,
        "_format_dt": _format_dt,
        "_format_timestamp": _format_timestamp,
        "_json_dumps": _json_dumps,
        "_json_loads": _json_loads,
        "behavior_rules": app_context.behavior_rules,
        "build_runtime_summary": lambda: build_runtime_summary(runtime_config),
        "calculate_focus_score": _calculate_focus_score,
        "current_stats": app_context.current_stats,
        "cv2": cv2,
        "event_storage": app_context.event_storage,
        "frame_lock": app_context.frame_lock,
        "get_model": get_model,
        "load_behavior_rules": load_behavior_rules,
        "map_detections_to_behaviors": map_detections_to_behaviors,
        "normalize_detections": normalize_detections,
        "on_runtime_settings_updated": lambda settings: None,
        "or_": or_,
        "runtime_lock": app_context.runtime_lock,
        "runtime_refs": app_context.runtime_refs,
        "save_alert_snapshot": save_alert_snapshot,
        "session_scope": session_scope,
        "source_lock": app_context.source_lock,
        "source_state": app_context.source_state,
        "stats_lock": app_context.stats_lock,
        "user_can_access_camera": lambda user=None: False,
    }
    deps.update(build_repository_helpers(deps))
    deps.update(build_config_services(deps))
    deps.update(build_report_services(deps))
    return create_upload_analysis_service(deps)


def get_worker_service():
    global _WORKER_SERVICE
    if _WORKER_SERVICE is None:
        _WORKER_SERVICE = _build_worker_service()
    return _WORKER_SERVICE


def run_upload_analysis_task(task: UploadAnalysisTask) -> None:
    service = get_worker_service()
    service.process_uploaded_video(task.job_id, task.user_id, task.file_path)
