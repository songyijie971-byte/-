import os
import threading

import cv2
from flask import abort, g, jsonify, redirect, request, session, url_for
from sqlalchemy import or_
from werkzeug.security import check_password_hash, generate_password_hash

from analysis_routes import register_analysis_routes
from analysis_service import build_analysis_services
from app_config import build_runtime_summary
from auth_routes import register_auth_routes
from auth_service import build_auth_services
from security_service import build_security_services
from app_core.job_executor import (
    ExecutorBackedUploadAnalysisDispatcher,
    LocalThreadJobExecutor,
    ProcessPoolJobExecutor,
    QueueJobExecutor,
)
from behavior_core import (
    BEHAVIOR_DISPLAY_NAMES,
    BEHAVIOR_RULES,
    BehaviorTemporalAnalyzer,
    map_detections_to_behaviors,
    normalize_detections,
)
from camera_service import build_camera_services
from config_routes import register_config_routes
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
from app_core.repositories import build_repository_helpers
from report_routes import register_report_routes
from report_service import build_report_services

ROLE_ADMIN = "admin"
ROLE_TEACHER = "teacher"
ROLE_USER = "user"


def _read_bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


CAMERA_ALLOWED_ROLES = {ROLE_ADMIN, ROLE_TEACHER}
if _read_bool_env("ALLOW_USER_CAMERA", False) or _read_bool_env("DEMO_ALLOW_CAMERA_FOR_ALL", False):
    CAMERA_ALLOWED_ROLES.add(ROLE_USER)


def build_service_registry(app, context, helpers):
    runtime_config = context.runtime_config
    deps = {
        "AlertEvent": AlertEvent,
        "ALLOWED_VIDEO_EXTENSIONS": set(runtime_config.allowed_video_extensions),
        "AnalysisReport": AnalysisReport,
        "BEHAVIOR_DISPLAY_NAMES": BEHAVIOR_DISPLAY_NAMES,
        "BEHAVIOR_RULES": BEHAVIOR_RULES,
        "BehaviorTemporalAnalyzer": BehaviorTemporalAnalyzer,
        "CAMERA_ALLOWED_ROLES": CAMERA_ALLOWED_ROLES,
        "CAMERA_BACKEND": runtime_config.camera_backend,
        "CAMERA_HEIGHT": runtime_config.camera_height,
        "CAMERA_INDEX": runtime_config.camera_index,
        "CAMERA_RETRY_SECONDS": runtime_config.camera_retry_seconds,
        "CAMERA_WIDTH": runtime_config.camera_width,
        "DEFAULT_ADMIN_PASSWORD": runtime_config.default_admin_password,
        "EXPERIMENT_OVERVIEW": EXPERIMENT_OVERVIEW,
        "HISTORY_REFRESH_INTERVAL_SECONDS": runtime_config.history_refresh_interval_seconds,
        "INFERENCE_EVERY_N_FRAMES": runtime_config.inference_every_n_frames,
        "INFERENCE_MIN_INTERVAL_SECONDS": runtime_config.inference_min_interval_seconds,
        "LOGGER": helpers["LOGGER"],
        "MAX_UPLOAD_BYTES": runtime_config.max_upload_bytes,
        "MODEL_PATH": runtime_config.model_path,
        "ROLE_ADMIN": ROLE_ADMIN,
        "ROLE_TEACHER": ROLE_TEACHER,
        "ROLE_USER": ROLE_USER,
        "STREAM_FPS": runtime_config.stream_fps,
        "SessionFactory": context.session_factory,
        "SystemConfig": SystemConfig,
        "UPLOAD_DIR": runtime_config.upload_dir,
        "User": User,
        "VIDEO_ANALYSIS_FRAME_STRIDE": runtime_config.video_analysis_frame_stride,
        "VideoAnalysisJob": VideoAnalysisJob,
        "YOLO_IMGSZ": runtime_config.yolo_imgsz,
        "_format_dt": helpers["_format_dt"],
        "_format_timestamp": helpers["_format_timestamp"],
        "_json_dumps": helpers["_json_dumps"],
        "_json_loads": helpers["_json_loads"],
        "abort": abort,
        "app": app,
        "behavior_rules": context.behavior_rules,
        "build_health_payload": helpers["build_health_payload"],
        "build_runtime_summary": lambda: build_runtime_summary(runtime_config),
        "calculate_focus_score": helpers["calculate_focus_score"],
        "check_password_hash": check_password_hash,
        "current_stats": context.current_stats,
        "cv2": cv2,
        "event_storage": context.event_storage,
        "frame_lock": context.frame_lock,
        "g": g,
        "generate_password_hash": generate_password_hash,
        "get_model": helpers["get_model"],
        "jsonify": jsonify,
        "load_behavior_rules": load_behavior_rules,
        "map_detections_to_behaviors": map_detections_to_behaviors,
        "normalize_detections": normalize_detections,
        "on_runtime_settings_updated": helpers["on_runtime_settings_updated"],
        "or_": or_,
        "redirect": redirect,
        "request": request,
        "runtime_refs": context.runtime_refs,
        "runtime_lock": context.runtime_lock,
        "session": session,
        "session_scope": session_scope,
        "source_lock": context.source_lock,
        "source_state": context.source_state,
        "stats_lock": context.stats_lock,
        "threading": threading,
        "url_for": url_for,
        "video_pipeline_lock": context.video_pipeline_lock,
    }

    deps.update(build_repository_helpers(deps))
    deps.update(build_security_services(deps))
    deps.update(build_auth_services(deps))
    deps.update(build_config_services(deps))
    deps.update(build_camera_services(deps))
    deps.update(build_report_services(deps))
    deps.update(build_analysis_services(deps))
    if runtime_config.job_executor_backend == "process":
        job_executor = ProcessPoolJobExecutor(
            logger=helpers["LOGGER"],
            handler_module="app_core.upload_analysis_worker",
            handler_name="run_upload_analysis_task",
            max_workers=runtime_config.job_executor_process_workers,
        )
    elif runtime_config.job_executor_backend == "queue":
        job_executor = QueueJobExecutor(
            logger=helpers["LOGGER"],
            queue_dir=runtime_config.job_queue_dir,
        )
    else:
        job_executor = LocalThreadJobExecutor(
            threading_module=threading,
            logger=helpers["LOGGER"],
            task_handler=deps["handle_upload_analysis_task"],
        )
    deps["job_executor"] = job_executor
    deps["upload_analysis_dispatcher"] = ExecutorBackedUploadAnalysisDispatcher(job_executor)

    register_auth_routes(app, deps)
    register_config_routes(app, deps)
    register_analysis_routes(app, deps)
    register_report_routes(app, deps)
    return deps
