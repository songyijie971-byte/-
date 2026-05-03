import os
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from app_config import mask_database_url
from behavior_core import BEHAVIOR_DISPLAY_NAMES, BehaviorTemporalAnalyzer
from database import (
    create_db_engine,
    create_session_factory,
    init_database,
    load_behavior_rules,
)
from storage import EventStorage


@dataclass
class AppContext:
    runtime_config: Any
    engine: Any
    session_factory: Any
    event_storage: EventStorage
    behavior_rules: Dict[str, Dict[str, object]]
    current_stats: Dict[str, object]
    source_state: Dict[str, object]
    runtime_refs: Dict[str, object]
    stats_lock: Any
    runtime_lock: Any
    frame_lock: Any
    source_lock: Any
    video_pipeline_lock: Any
    model_lock: Any
    model: Optional[Any] = None


def create_app_context(
    runtime_config,
    logger,
    initial_camera_status_factory: Callable[[], Dict[str, object]],
    initial_model_state_factory: Callable[[], Dict[str, object]],
) -> AppContext:
    try:
        engine = create_db_engine(runtime_config.database_url)
        session_factory = create_session_factory(engine)
        init_database(engine, session_factory)
    except Exception as exc:
        masked_database_url = mask_database_url(runtime_config.database_url)
        logger.exception("Failed to initialize database %s", masked_database_url)
        raise RuntimeError(
            "数据库初始化失败，请检查 DATABASE_URL 或 MySQL 配置。当前连接: {}".format(
                masked_database_url
            )
        ) from exc

    try:
        os.makedirs(runtime_config.upload_dir, exist_ok=True)
    except OSError as exc:
        logger.exception("Failed to create upload directory %s", runtime_config.upload_dir)
        raise RuntimeError(
            "上传目录创建失败，请检查 UPLOAD_DIR 配置: {}".format(
                runtime_config.upload_dir
            )
        ) from exc

    try:
        os.makedirs(runtime_config.job_queue_dir, exist_ok=True)
    except OSError as exc:
        logger.exception("Failed to create job queue directory %s", runtime_config.job_queue_dir)
        raise RuntimeError(
            "任务队列目录创建失败，请检查 JOB_QUEUE_DIR 配置: {}".format(
                runtime_config.job_queue_dir
            )
        ) from exc

    event_storage = EventStorage(session_factory=session_factory)
    behavior_rules = load_behavior_rules(session_factory)
    temporal_analyzer = BehaviorTemporalAnalyzer(behavior_rules)

    stats_lock = threading.Lock()
    runtime_lock = threading.Lock()
    frame_lock = threading.Lock()
    source_lock = threading.Lock()
    video_pipeline_lock = threading.Lock()
    model_lock = threading.Lock()

    initial_camera_status = initial_camera_status_factory()
    current_stats = {
        "stable_counts": {key: 0 for key in BEHAVIOR_DISPLAY_NAMES},
        "durations": {key: 0.0 for key in BEHAVIOR_DISPLAY_NAMES},
        "alerts": [],
        "behavior_details": {},
        "frame_behaviors": {},
        "detections": [],
        "latest_snapshot": None,
        "focus_score": {},
        "last_updated": None,
        "camera_status": dict(initial_camera_status),
    }
    source_state = {"mode": "camera", "label": "实时监控"}
    runtime_refs = {
        "temporal_analyzer": temporal_analyzer,
        "last_public_history_refresh_at": 0.0,
        "latest_camera_frame": None,
        "image_analysis_records_by_user": {},
        "video_pipeline_started": False,
        "camera_reconnect_requested": False,
        "runtime_profile_key": "balanced",
        "runtime_settings": {
            "yolo_imgsz": runtime_config.yolo_imgsz,
            "stream_fps": runtime_config.stream_fps,
            "camera_index": runtime_config.camera_index,
            "camera_width": runtime_config.camera_width,
            "camera_height": runtime_config.camera_height,
            "inference_every_n_frames": runtime_config.inference_every_n_frames,
            "inference_min_interval_seconds": runtime_config.inference_min_interval_seconds,
            "video_analysis_frame_stride": runtime_config.video_analysis_frame_stride,
            "max_upload_size_mb": round(runtime_config.max_upload_bytes / 1024 / 1024),
        },
        "camera_status": initial_camera_status_factory(),
        "model_state": initial_model_state_factory(),
    }

    return AppContext(
        runtime_config=runtime_config,
        engine=engine,
        session_factory=session_factory,
        event_storage=event_storage,
        behavior_rules=behavior_rules,
        current_stats=current_stats,
        source_state=source_state,
        runtime_refs=runtime_refs,
        stats_lock=stats_lock,
        runtime_lock=runtime_lock,
        frame_lock=frame_lock,
        source_lock=source_lock,
        video_pipeline_lock=video_pipeline_lock,
        model_lock=model_lock,
    )
