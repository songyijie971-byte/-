import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, Optional

from app_core.inference_runtime import predict_with_preferred_device


class UploadAnalysisValidationError(Exception):
    def __init__(self, message: str, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True)
class AnalysisRepositories:
    query_jobs_for_user: Callable
    get_latest_job_for_user: Callable
    get_visible_job: Callable
    get_job_by_id: Callable
    create_upload_job_record: Callable
    delete_job_artifacts: Callable
    get_or_create_report: Callable
    get_report_for_job_and_user: Callable
    get_latest_reportable_job_for_user: Callable
    count_jobs_for_user_by_status: Callable
    count_completed_reports_for_user: Callable


@dataclass(frozen=True)
class AnalysisReportBuilders:
    build_behavior_report_rows: Callable
    build_report_insights: Callable
    build_risk_assessment: Callable
    build_teacher_suggestions: Callable
    build_report_gallery: Callable
    build_rule_snapshot_for_report: Callable
    build_analysis_metrics: Callable
    serialize_job: Callable
    job_status_message: Callable


@dataclass(frozen=True)
class AnalysisRuntimeContext:
    behavior_display_names: Dict[str, str]
    session_factory: Callable
    session_scope: Callable
    load_behavior_rules: Callable
    event_storage: object
    get_model: Callable
    normalize_detections: Callable
    map_detections_to_behaviors: Callable
    save_alert_snapshot: Callable
    calculate_focus_score: Callable
    user_can_access_camera: Callable
    json_dumps: Callable
    json_loads: Callable
    format_timestamp: Callable
    format_datetime: Callable
    upload_dir: str
    allowed_image_extensions: set
    allowed_video_extensions: set
    logger: object
    cv2: object
    stats_lock: object
    current_stats: Dict[str, object]
    source_lock: object
    source_state: Dict[str, object]
    get_behavior_rule_config_payload: Callable
    get_runtime_setting: Callable


class UploadAnalysisApplicationService:
    def __init__(
        self,
        runtime: AnalysisRuntimeContext,
        repositories: AnalysisRepositories,
        report_builders: AnalysisReportBuilders,
        temporal_analyzer_factory: Callable,
    ) -> None:
        self.runtime = runtime
        self.repositories = repositories
        self.report_builders = report_builders
        self.temporal_analyzer_factory = temporal_analyzer_factory

    def video_analysis_frame_stride(self) -> int:
        return max(1, int(self.runtime.get_runtime_setting("video_analysis_frame_stride") or 1))

    def yolo_imgsz(self) -> int:
        return max(64, int(self.runtime.get_runtime_setting("yolo_imgsz") or 416))

    def empty_analysis_status(self, user) -> Dict[str, object]:
        return {
            "status": "idle",
            "status_label": "空闲",
            "status_detail": "当前没有正在处理的上传分析任务。",
            "message": "暂无分析任务",
            "filename": None,
            "job_id": None,
            "progress": 0.0,
            "processed_frames": 0,
            "total_frames": 0,
            "report_ready": False,
            "report_url": None,
            "source_url": None,
            "source_mode": "upload",
            "source_label": "上传分析",
            "error_code": None,
            "error_message": None,
            "failure_stage": None,
            "queued_at": "--",
            "started_at": "--",
            "finished_at": "--",
            "deleted_at": "--",
            "created_at": "--",
            "updated_at": "--",
        }

    def allowed_video_file(self, filename: str) -> bool:
        _, ext = os.path.splitext(filename.lower())
        return ext in self.runtime.allowed_video_extensions

    def allowed_image_file(self, filename: str) -> bool:
        _, ext = os.path.splitext(filename.lower())
        return ext in self.runtime.allowed_image_extensions

    def query_jobs_for_user(self, db, user):
        return self.repositories.query_jobs_for_user(db, user)

    def get_latest_job_for_user(self, db, user):
        return self.repositories.get_latest_job_for_user(db, user)

    def get_visible_job(self, db, user, job_id, include_deleted: bool = False):
        return self.repositories.get_visible_job(db, user, job_id, include_deleted=include_deleted)

    def update_job_record(self, job_id: str, **fields) -> bool:
        with self.runtime.session_scope(self.runtime.session_factory) as db:
            job = self.repositories.get_job_by_id(db, job_id)
            if job is None:
                return False
            if job.status == "deleted":
                self.runtime.logger.info(
                    "Skip updating deleted upload analysis job=%s fields=%s",
                    job_id,
                    sorted(fields.keys()),
                )
                return False
            for key, value in fields.items():
                setattr(job, key, value)
            return True

    def purge_job_artifacts(self, job_id: str, user_id: int) -> None:
        with self.runtime.session_scope(self.runtime.session_factory) as db:
            self.repositories.delete_job_artifacts(db, job_id, user_id)

    def is_job_deleted(self, job_id: str) -> bool:
        with self.runtime.session_scope(self.runtime.session_factory) as db:
            job = self.repositories.get_job_by_id(db, job_id)
            return bool(job is None or job.status == "deleted")

    def save_report_record(
        self,
        job_id: str,
        user_id: int,
        report_payload: Dict[str, object],
    ) -> bool:
        with self.runtime.session_scope(self.runtime.session_factory) as db:
            job = self.repositories.get_job_by_id(db, job_id)
            if job is None or job.status == "deleted":
                self.runtime.logger.info(
                    "Skip saving report for deleted or missing upload analysis job=%s",
                    job_id,
                )
                return False
            report = self.repositories.get_or_create_report(db, job_id, user_id)
            report.generated_at = datetime.utcnow()
            report.focus_score_json = self.runtime.json_dumps(report_payload.get("focus_score", {}))
            report.summary_json = self.runtime.json_dumps(report_payload.get("summary", {}))
            report.behavior_rows_json = self.runtime.json_dumps(report_payload.get("behavior_rows", []))
            report.insights_json = self.runtime.json_dumps(report_payload.get("insights", []))
            report.risk_level = report_payload.get("risk_level", "")
            report.risk_summary = report_payload.get("risk_summary", "")
            report.teacher_suggestions_json = self.runtime.json_dumps(
                report_payload.get("teacher_suggestions", [])
            )
            report.gallery_items_json = self.runtime.json_dumps(
                report_payload.get("gallery_items", [])
            )
            report.rule_snapshot_json = self.runtime.json_dumps(
                report_payload.get("rule_snapshot", {})
            )
            report.analysis_metrics_json = self.runtime.json_dumps(
                report_payload.get("analysis_metrics", {})
            )
            return True

    def create_upload_job(
        self,
        user_id: int,
        original_filename: str,
        stored_filename: str,
        source_path: str,
        source_size_bytes: int = 0,
    ) -> str:
        job_id = uuid.uuid4().hex
        now = datetime.utcnow()
        with self.runtime.session_scope(self.runtime.session_factory) as db:
            self.repositories.create_upload_job_record(
                db,
                job_id=job_id,
                user_id=user_id,
                original_filename=original_filename,
                stored_filename=stored_filename,
                source_path=source_path,
                status="queued",
                progress=0.0,
                processed_frames=0,
                total_frames=0,
                duration_seconds=0.0,
                fps=0.0,
                frame_stride=self.video_analysis_frame_stride(),
                report_ready=False,
                source_size_bytes=int(source_size_bytes or 0),
                status_detail="任务已创建，等待后台分析。",
                queued_at=now,
            )
        return job_id

    def analyze_uploaded_results(
        self,
        results,
        timestamp: float,
        snapshot_frame,
        analyzer,
        user_id: int,
        job_id: str,
    ) -> Dict[str, object]:
        model = self.runtime.get_model()
        detections = self.runtime.normalize_detections(results[0], model.names, timestamp)
        frame_behaviors = self.runtime.map_detections_to_behaviors(detections)

        def handle_alert(alert_payload):
            self.runtime.save_alert_snapshot(
                snapshot_frame,
                alert_payload,
                user_id=user_id,
                job_id=job_id,
            )

        temporal_state = analyzer.update(frame_behaviors, timestamp, alert_callback=handle_alert)
        return self.runtime.calculate_focus_score(temporal_state["stable_counts"])

    def analyze_uploaded_image(
        self,
        file_path: str,
        original_filename: str,
        source_relative_path: str,
        source_size_bytes: int = 0,
    ) -> Dict[str, object]:
        if not os.path.exists(file_path):
            raise FileNotFoundError("上传图片不存在或已被移动，请重新上传。")

        frame = self.runtime.cv2.imread(file_path)
        if frame is None:
            raise ValueError("无法读取当前图片文件，请确认文件完整且格式受支持。")

        height, width = frame.shape[:2]
        model = self.runtime.get_model()
        timestamp = time.time()
        results = predict_with_preferred_device(
            model,
            frame,
            logger=self.runtime.logger,
            conf=0.35,
            iou=0.45,
            imgsz=self.yolo_imgsz(),
            verbose=False,
        )
        detections = self.runtime.normalize_detections(results[0], model.names, timestamp)
        frame_behaviors = self.runtime.map_detections_to_behaviors(detections)
        stable_counts = {
            behavior_key: int(frame_behaviors.get(behavior_key).count if frame_behaviors.get(behavior_key) else 0)
            for behavior_key in self.runtime.behavior_display_names
        }
        focus_snapshot = self.runtime.calculate_focus_score(stable_counts)

        source_relative_path = source_relative_path.replace("\\", "/")
        relative_stem, _ = os.path.splitext(source_relative_path)
        annotated_relative_path = "{}_annotated.jpg".format(relative_stem)
        annotated_relative_path = annotated_relative_path.replace("\\", "/")
        annotated_path = os.path.join(
            self.runtime.upload_dir,
            *annotated_relative_path.split("/"),
        )
        os.makedirs(os.path.dirname(annotated_path), exist_ok=True)
        annotated_frame = results[0].plot()
        if not self.runtime.cv2.imwrite(annotated_path, annotated_frame):
            raise ValueError("图片分析结果生成失败，无法写入标注图片。")

        behavior_items = []
        for behavior_key, behavior in frame_behaviors.items():
            if int(behavior.count) <= 0:
                continue
            behavior_items.append(
                {
                    "behavior_key": behavior_key,
                    "behavior_name": behavior.behavior_name,
                    "count": int(behavior.count),
                    "confidence": round(float(behavior.confidence), 3),
                    "source_class_ids": list(behavior.source_class_ids),
                }
            )
        behavior_items.sort(
            key=lambda item: (int(item["count"]), float(item["confidence"])),
            reverse=True,
        )

        detections_payload = []
        for detection in detections[:12]:
            detections_payload.append(
                {
                    "class_id": int(detection.class_id),
                    "class_name": detection.class_name,
                    "confidence": round(float(detection.confidence), 3),
                    "bbox": [round(float(value), 1) for value in detection.bbox],
                }
            )

        summary_message = "图片分析完成，已输出当前画面的单帧识别结果。"
        if behavior_items:
            summary_message = "图片分析完成，检测到 {} 类课堂行为，共 {} 个目标。".format(
                len(behavior_items),
                len(detections),
            )
        elif detections_payload:
            summary_message = "图片分析完成，已检测到目标，但暂未映射到课堂行为标签。"

        return {
            "analysis_type": "image",
            "status": "completed",
            "status_label": "已完成",
            "progress": 100.0,
            "message": summary_message,
            "status_detail": "图片模式基于单帧识别，只展示当前画面中的检测结果，不生成连续帧告警与时序报告。",
            "source_mode": "image",
            "source_label": "上传图片",
            "filename": original_filename,
            "source_size_bytes": int(source_size_bytes or 0),
            "image_width": int(width),
            "image_height": int(height),
            "detections_count": len(detections),
            "detections": detections_payload,
            "behavior_items": behavior_items,
            "focus_score": focus_snapshot,
            "source_url": "/image-uploads/{}".format(source_relative_path),
            "annotated_url": "/image-uploads/{}".format(annotated_relative_path),
            "source_relative_path": source_relative_path,
            "annotated_relative_path": annotated_relative_path,
            "report_ready": False,
            "analysis_note": "单张图片无法触发“连续帧阈值”和“持续时长”规则，因此该模式适用于展示模型静态识别能力。",
            "analyzed_at": self.runtime.format_datetime(datetime.utcnow()),
        }

    def process_uploaded_video(self, job_id: str, user_id: int, file_path: str) -> None:
        upload_analyzer = self.temporal_analyzer_factory(
            self.runtime.load_behavior_rules(self.runtime.session_factory)
        )
        focus_snapshot = self.runtime.calculate_focus_score(
            {key: 0 for key in self.runtime.behavior_display_names}
        )
        processing_started_at = time.perf_counter()
        last_progress_persisted = 0.0
        last_progress_persisted_at = processing_started_at
        now = datetime.utcnow()
        current_stage = "prepare"
        self.runtime.logger.info("Upload analysis job=%s stage=%s", job_id, current_stage)

        self.update_job_record(
            job_id,
            status="processing",
            status_detail="任务已启动，正在准备分析环境。",
            progress=0.0,
            processed_frames=0,
            total_frames=0,
            report_ready=False,
            failure_stage=None,
            error_code=None,
            error_message=None,
            started_at=now,
            finished_at=None,
            deleted_at=None,
        )

        cap = None
        try:
            if not os.path.exists(file_path):
                raise FileNotFoundError("上传文件不存在或已被移动，请重新上传视频。")

            current_stage = "open_video"
            self.runtime.logger.info("Upload analysis job=%s stage=%s", job_id, current_stage)
            self.update_job_record(job_id, status_detail="已读取任务文件，正在打开视频。")
            cap = self.runtime.cv2.VideoCapture(file_path)
            if not cap.isOpened():
                raise ValueError("无法读取当前视频文件，请确认文件完整且格式受支持。")

            total_frames = int(cap.get(self.runtime.cv2.CAP_PROP_FRAME_COUNT) or 0)
            fps = float(cap.get(self.runtime.cv2.CAP_PROP_FPS) or 0.0)
            if fps <= 0:
                fps = 25.0

            duration_seconds = (total_frames / fps) if total_frames > 0 and fps > 0 else 0.0

            def _read_limit_float(name: str, default: float) -> float:
                raw = os.getenv(name, str(default))
                try:
                    return max(0.0, float(raw))
                except (TypeError, ValueError):
                    return float(default)

            def _read_limit_int(name: str, default: int) -> int:
                raw = os.getenv(name, str(default))
                try:
                    return max(0, int(raw))
                except (TypeError, ValueError):
                    return int(default)

            max_duration_seconds = _read_limit_float("MAX_VIDEO_DURATION_SECONDS", 3600.0)
            max_total_frames = _read_limit_int("MAX_VIDEO_FRAMES", 300000)
            if max_duration_seconds and duration_seconds and duration_seconds > max_duration_seconds:
                raise UploadAnalysisValidationError(
                    "视频时长超过限制（{:.1f}s > {:.0f}s），请上传更短视频或调整 MAX_VIDEO_DURATION_SECONDS。".format(
                        duration_seconds,
                        max_duration_seconds,
                    ),
                    error_code="video_too_long",
                )
            if max_total_frames and total_frames and total_frames > max_total_frames:
                raise UploadAnalysisValidationError(
                    "视频帧数超过限制（{} > {}），请上传更短视频或调整 MAX_VIDEO_FRAMES。".format(
                        total_frames,
                        max_total_frames,
                    ),
                    error_code="video_too_many_frames",
                )
            self.update_job_record(
                job_id,
                total_frames=total_frames,
                fps=round(fps, 2),
                frame_stride=self.video_analysis_frame_stride(),
                duration_seconds=round(duration_seconds, 1),
                status_detail="瑙嗛宸叉墦寮€锛屾鍦ㄥ姞杞藉垎鏋愭ā鍨嬨€?",
            )

            frame_index = 0
            processed_frames = 0
            current_stage = "load_model"
            self.runtime.logger.info("Upload analysis job=%s stage=%s", job_id, current_stage)
            model = self.runtime.get_model()
            analysis_base_timestamp = time.time()

            current_stage = "frame_inference"
            self.runtime.logger.info("Upload analysis job=%s stage=%s", job_id, current_stage)
            self.update_job_record(job_id, status_detail="模型已加载，正在抽帧分析视频内容。")

            while True:
                if self.is_job_deleted(job_id):
                    self.purge_job_artifacts(job_id, user_id)
                    self.runtime.logger.info("Upload analysis job=%s deleted=true", job_id)
                    return

                success, frame = cap.read()
                if not success:
                    break

                frame_index += 1
                current_frame_stride = self.video_analysis_frame_stride()
                if frame_index % current_frame_stride != 0:
                    continue

                timestamp = analysis_base_timestamp + (frame_index / fps)
                results = predict_with_preferred_device(
                    model,
                    frame,
                    logger=self.runtime.logger,
                    conf=0.35,
                    iou=0.45,
                    imgsz=self.yolo_imgsz(),
                    verbose=False,
                )
                plotted = results[0].plot()
                focus_snapshot = self.analyze_uploaded_results(
                    results,
                    timestamp,
                    plotted,
                    upload_analyzer,
                    user_id,
                    job_id,
                )

                processed_frames = frame_index
                progress = 0.0
                if total_frames > 0:
                    progress = min(100.0, round((processed_frames / total_frames) * 100, 1))

                now_perf = time.perf_counter()
                should_persist_progress = (
                    progress >= 100.0
                    or (progress - last_progress_persisted) >= 1.0
                    or (now_perf - last_progress_persisted_at) >= 0.5
                )
                if not should_persist_progress:
                    continue

                self.update_job_record(
                    job_id,
                    status="processing",
                    processed_frames=processed_frames,
                    total_frames=total_frames,
                    progress=progress,
                    duration_seconds=round(duration_seconds, 1),
                    fps=round(fps, 2),
                    status_detail="姝ｅ湪鍒嗘瀽瑙嗛甯у苟姹囨€昏鍫傝涓轰簨浠躲€?",
                )
                last_progress_persisted = progress
                last_progress_persisted_at = now_perf

            if self.is_job_deleted(job_id):
                self.purge_job_artifacts(job_id, user_id)
                self.runtime.logger.info("Upload analysis job=%s deleted=true", job_id)
                return

            current_stage = "report_generation"
            self.runtime.logger.info("Upload analysis job=%s stage=%s", job_id, current_stage)
            self.update_job_record(job_id, status_detail="鍒嗘瀽瀹屾垚锛屾鍦ㄧ敓鎴愬垎鏋愭姤鍛娿€?")
            report_events = self.runtime.event_storage.list_events(
                limit=500,
                user_id=user_id,
                job_id=job_id,
            )
            report_summary = self.runtime.event_storage.build_history_summary(
                user_id=user_id,
                job_id=job_id,
                recent_limit=20,
                timeline_limit=20,
            )
            behavior_rows = self.report_builders.build_behavior_report_rows(report_events)
            insights = self.report_builders.build_report_insights(
                report_summary,
                focus_snapshot,
                behavior_rows,
                duration_seconds,
            )
            risk_assessment = self.report_builders.build_risk_assessment(
                report_summary,
                focus_snapshot,
                behavior_rows,
            )
            teacher_suggestions = self.report_builders.build_teacher_suggestions(
                report_summary,
                focus_snapshot,
                behavior_rows,
            )
            gallery_items = self.report_builders.build_report_gallery(report_events)
            analysis_metrics = self.report_builders.build_analysis_metrics(
                total_frames=total_frames,
                processed_frames=processed_frames,
                duration_seconds=duration_seconds,
                started_at=processing_started_at,
                finished_at=time.perf_counter(),
            )

            report_payload = {
                "focus_score": focus_snapshot,
                "summary": report_summary,
                "behavior_rows": behavior_rows,
                "insights": insights,
                "risk_level": risk_assessment["risk_level"],
                "risk_summary": risk_assessment["risk_summary"],
                "teacher_suggestions": teacher_suggestions,
                "gallery_items": gallery_items,
                "rule_snapshot": self.report_builders.build_rule_snapshot_for_report(),
                "analysis_metrics": analysis_metrics,
            }
            if self.is_job_deleted(job_id):
                self.purge_job_artifacts(job_id, user_id)
                self.runtime.logger.info(
                    "Upload analysis job=%s deleted=true before report persistence",
                    job_id,
                )
                return

            report_saved = self.save_report_record(job_id, user_id, report_payload)
            if not report_saved:
                self.purge_job_artifacts(job_id, user_id)
                self.runtime.logger.info(
                    "Upload analysis job=%s report persistence skipped for deleted job",
                    job_id,
                )
                return

            if self.is_job_deleted(job_id):
                self.purge_job_artifacts(job_id, user_id)
                self.runtime.logger.info(
                    "Upload analysis job=%s deleted=true before completion update",
                    job_id,
                )
                return

            updated = self.update_job_record(
                job_id,
                status="completed",
                progress=100.0,
                processed_frames=processed_frames,
                total_frames=total_frames,
                duration_seconds=round(duration_seconds, 1),
                fps=round(fps, 2),
                report_ready=True,
                status_detail="鍒嗘瀽瀹屾垚锛屾姤鍛婂凡鐢熸垚锛屽彲鐩存帴鎵撳紑鍒嗘瀽鎶ュ憡銆?",
                finished_at=datetime.utcnow(),
                failure_stage=None,
                error_code=None,
                error_message=None,
            )
            if not updated:
                self.purge_job_artifacts(job_id, user_id)
                self.runtime.logger.info(
                    "Upload analysis job=%s completion update skipped for deleted job",
                    job_id,
                )
                return
            elapsed = time.perf_counter() - processing_started_at
            self.runtime.logger.info(
                "Upload analysis job=%s stage=completed elapsed=%.2fs", job_id, elapsed
            )
        except Exception as exc:
            self.runtime.logger.exception("Failed to process uploaded video job=%s", job_id)
            stage_message_map = {
                "prepare": "????????????????",
                "open_video": "???????????????????????",
                "load_model": "????????????????????",
                "frame_inference": "??????????????????",
                "report_generation": "?????????????????",
            }
            error_code = "analysis_failed"
            if isinstance(exc, UploadAnalysisValidationError):
                error_code = exc.error_code
                stage_message_map[current_stage] = str(exc)
            self.update_job_record(
                job_id,
                status="failed",
                report_ready=False,
                finished_at=datetime.utcnow(),
                failure_stage=current_stage,
                error_code=error_code,
                error_message=str(exc),
                status_detail=stage_message_map.get(
                    current_stage,
                    "浠诲姟鎵ц澶辫触锛岃閲嶆柊涓婁紶瑙嗛銆?",
                ),
            )
            elapsed = time.perf_counter() - processing_started_at
            self.runtime.logger.info(
                "Upload analysis job=%s stage=%s elapsed=%.2fs status=failed",
                job_id,
                current_stage,
                elapsed,
            )
        finally:
            if cap is not None:
                cap.release()

    def build_analysis_status_for_user(self, user, job_id: Optional[str] = None) -> Dict[str, object]:
        with self.runtime.session_scope(self.runtime.session_factory) as db:
            job = self.get_visible_job(db, user, job_id) if job_id else self.get_latest_job_for_user(db, user)
            if job is None:
                return self.empty_analysis_status(user)

            payload = self.report_builders.serialize_job(job)
            payload["message"] = self.report_builders.job_status_message(job)
            payload["source_mode"] = "upload"
            payload["source_label"] = "????"
            return payload

    def build_history_response_for_user(self, user) -> Dict[str, object]:
        include_public = self.runtime.user_can_access_camera(user)
        events = self.runtime.event_storage.list_events(
            limit=10,
            user_id=user["id"],
            include_public=include_public,
        )
        summary = self.runtime.event_storage.build_history_summary(
            user_id=user["id"],
            include_public=include_public,
        )
        latest_snapshot = self.runtime.event_storage.get_latest_snapshot(
            user_id=user["id"],
            include_public=include_public,
        )

        if include_public:
            with self.runtime.stats_lock:
                current_focus = dict(self.runtime.current_stats["focus_score"])
        else:
            with self.runtime.session_scope(self.runtime.session_factory) as db:
                latest_job = self.get_latest_job_for_user(db, user)
                if latest_job and latest_job.report_ready:
                    report = self.repositories.get_report_for_job_and_user(
                        db,
                        latest_job.job_id,
                        user["id"],
                    )
                    current_focus = (
                        self.runtime.json_loads(
                            report.focus_score_json,
                            self.runtime.calculate_focus_score({}),
                        )
                        if report
                        else self.runtime.calculate_focus_score({})
                    )
                else:
                    current_focus = self.runtime.calculate_focus_score({})

        return {
            "events": [
                dict(event, timestamp_label=self.runtime.format_timestamp(event.get("timestamp")))
                for event in events
            ],
            "summary": summary,
            "latest_snapshot": latest_snapshot,
            "current_focus": current_focus,
        }

    def build_stats_response(self) -> Dict[str, object]:
        with self.runtime.source_lock:
            source_mode = self.runtime.source_state["mode"]
            source_label = self.runtime.source_state["label"]

        with self.runtime.stats_lock:
            stable_counts = dict(self.runtime.current_stats["stable_counts"])
            durations = dict(self.runtime.current_stats["durations"])
            return {
                "low_head": stable_counts.get("low_head", 0),
                "sleep": stable_counts.get("sleep", 0),
                "hand_raise": stable_counts.get("hand_raise", 0),
                "turn_talk": stable_counts.get("turn_talk", 0),
                "head_up": stable_counts.get("head_up", 0),
                "durations": durations,
                "alerts": list(self.runtime.current_stats["alerts"]),
                "behavior_details": dict(self.runtime.current_stats["behavior_details"]),
                "focus_score": dict(self.runtime.current_stats["focus_score"]),
                "latest_snapshot": self.runtime.current_stats["latest_snapshot"],
                "last_updated": self.runtime.current_stats["last_updated"],
                "source_mode": source_mode,
                "source_label": source_label,
                "camera_status": dict(self.runtime.current_stats.get("camera_status", {})),
            }

    def build_dashboard_payload(self, user) -> Dict[str, object]:
        stats = self.build_stats_response()
        history = self.build_history_response_for_user(user)
        rule_payload = self.runtime.get_behavior_rule_config_payload()

        with self.runtime.session_scope(self.runtime.session_factory) as db:
            latest_job = self.get_latest_job_for_user(db, user)
            latest_report_job = (
                latest_job
                if latest_job and latest_job.report_ready
                else self.repositories.get_latest_reportable_job_for_user(db, user)
            )
            queued_count = self.repositories.count_jobs_for_user_by_status(
                db,
                user,
                ["queued", "processing"],
            )
            completed_count = self.repositories.count_completed_reports_for_user(db, user)

        summary = history.get("summary", {})
        recent_alerts = history.get("events", [])[:5]
        focus = history.get("current_focus") or stats.get("focus_score") or self.runtime.calculate_focus_score({})
        focus_level = focus.get("level", "?")
        latest_snapshot = history.get("latest_snapshot") or stats.get("latest_snapshot")

        latest_report = None
        if latest_report_job:
            latest_report = {
                "job_id": latest_report_job.job_id,
                "filename": latest_report_job.original_filename,
                "report_url": "/report/{}".format(latest_report_job.job_id),
                "updated_at": self.runtime.format_datetime(latest_report_job.updated_at),
            }

        return {
            "system_status": {
                "source_label": stats.get("source_label", "????"),
                "source_mode": stats.get("source_mode", "camera"),
                "focus_level": focus_level,
                "focus_score": focus.get("score", 0),
                "last_updated": stats.get("last_updated"),
                "alert_count": len(stats.get("alerts", [])),
                "queued_jobs": queued_count,
                "completed_reports": completed_count,
                "camera_status": stats.get("camera_status", {}),
            },
            "latest_job": self.report_builders.serialize_job(latest_job) if latest_job else None,
            "latest_report": latest_report,
            "recent_alerts": recent_alerts,
            "focus_summary": {
                "score": focus.get("score", 0),
                "level": focus_level,
                "summary_text": focus.get("summary_text", "--"),
                "rule_text": focus.get("rule_text", "--"),
                "limits_text": focus.get("limits_text", "--"),
            },
            "focus_disclaimer": "???????????????????????????????",
            "rule_summary": {
                "version_label": rule_payload.get("version_label", "--"),
                "items": rule_payload.get("items", [])[:4],
                "runtime_parameters": rule_payload.get("runtime_parameters", [])[:5],
            },
            "history_summary": summary,
            "top_behaviors": summary.get("behavior_totals", [])[:4],
            "latest_snapshot": latest_snapshot,
            "latest_snapshot_label": (
                self.runtime.format_timestamp(latest_snapshot.get("timestamp"))
                if latest_snapshot
                else "--"
            ),
            "timeline": summary.get("recent_timeline", []),
            "trend_chart": summary.get("trend_chart", []),
        }
