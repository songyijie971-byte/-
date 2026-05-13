import os
import secrets
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Tuple

from database import build_database_url

DEFAULT_ALLOWED_VIDEO_EXTENSIONS = (".mp4", ".avi", ".mov", ".mkv", ".webm")
DEFAULT_ALLOWED_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
SUPPORTED_CAMERA_BACKENDS = {"auto", "default", "dshow", "msmf", "any"}


def load_flask_secret_key(upload_dir: str) -> str:
    explicit = os.getenv("FLASK_SECRET_KEY")
    if explicit:
        return explicit

    secret_file = os.getenv("FLASK_SECRET_KEY_FILE")
    if secret_file:
        secret_path = Path(secret_file)
    else:
        secret_path = Path(upload_dir) / ".." / "runtime" / "flask_secret_key.txt"

    secret_path = secret_path.resolve()
    secret_path.parent.mkdir(parents=True, exist_ok=True)

    if secret_path.exists():
        value = secret_path.read_text(encoding="utf-8").strip()
        if value:
            return value

    value = secrets.token_hex(32)
    secret_path.write_text(value, encoding="utf-8")
    return value


def _read_int(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)


def _read_float(name: str, default: float, minimum: float = 0.0) -> float:
    raw = os.getenv(name, str(default))
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)


@dataclass(frozen=True)
class RuntimeConfig:
    database_url: str
    inference_provider: str
    model_path: str
    roboflow_model_id: str
    roboflow_api_key_present: bool
    yolo_confidence: float
    yolo_imgsz: int
    inference_every_n_frames: int
    inference_min_interval_seconds: float
    stream_fps: float
    camera_index: int
    camera_width: int
    camera_height: int
    camera_backend: str
    history_refresh_interval_seconds: float
    camera_retry_seconds: float
    video_analysis_frame_stride: int
    upload_dir: str
    allowed_video_extensions: Tuple[str, ...]
    allowed_image_extensions: Tuple[str, ...]
    flask_secret_key: str
    default_admin_password: str
    max_upload_size_mb: int
    max_upload_bytes: int
    job_executor_backend: str
    job_executor_process_workers: int
    job_queue_dir: str
    job_queue_poll_seconds: float
    startup_checks: Dict[str, Dict[str, object]]


def mask_database_url(database_url: str) -> str:
    if database_url.startswith("sqlite"):
        return database_url

    scheme, sep, remainder = database_url.partition("://")
    if not sep:
        return database_url

    credentials, at_sep, host = remainder.partition("@")
    if at_sep and ":" in credentials:
        username, _, _ = credentials.partition(":")
        return "{}://{}:{}@{}".format(scheme, username, "***", host)
    return database_url


def load_runtime_config() -> RuntimeConfig:
    model_path = os.getenv("YOLO_MODEL_PATH", "best.onnx")
    roboflow_model_id = os.getenv(
        "ROBOFLOW_MODEL_ID",
        "new-student-classroom-activity-3-hand-raise-phone-sleep-2-x63gb-6j0xy/6",
    )
    roboflow_api_key_present = bool(os.getenv("ROBOFLOW_API_KEY", "").strip())
    inference_provider = (
        os.getenv("INFERENCE_PROVIDER")
        or os.getenv("MODEL_PROVIDER")
        or ("roboflow" if roboflow_api_key_present else "local")
    ).strip().lower()
    if inference_provider not in {"local", "roboflow"}:
        inference_provider = "local"

    upload_dir = os.getenv("UPLOAD_DIR", "data/uploads")
    camera_backend = os.getenv("CAMERA_BACKEND", "auto").lower()
    if camera_backend not in SUPPORTED_CAMERA_BACKENDS:
        camera_backend = "auto"

    max_upload_size_mb = _read_int("MAX_UPLOAD_SIZE_MB", 200, minimum=1)
    job_executor_backend = os.getenv("JOB_EXECUTOR_BACKEND", "thread").strip().lower()
    if job_executor_backend not in {"thread", "process", "queue"}:
        job_executor_backend = "thread"
    job_executor_process_workers = _read_int("JOB_EXECUTOR_PROCESS_WORKERS", 2, minimum=1)
    job_queue_dir = os.getenv("JOB_QUEUE_DIR", "data/job_queue")
    job_queue_poll_seconds = _read_float("JOB_QUEUE_POLL_SECONDS", 1.0, minimum=0.1)

    startup_checks = {
        "model": {
            "status": "ok" if os.path.exists(model_path) else "warning",
            "message": (
                "模型文件已就绪。"
                if os.path.exists(model_path)
                else "未找到模型文件，实时监测和视频分析会在调用时提示错误。"
            ),
            "path": model_path,
        },
        "upload_dir": {
            "status": "configured",
            "message": "上传目录将在启动时自动创建。",
            "path": upload_dir,
        },
        "database": {
            "status": "configured",
            "message": "数据库连接参数已装载。",
            "url": mask_database_url(build_database_url()),
        },
        "job_executor": {
            "status": "configured",
            "message": "Background job executor configuration loaded.",
            "backend": job_executor_backend,
            "process_workers": job_executor_process_workers,
        },
        "job_queue": {
            "status": "configured",
            "message": "Job queue configuration loaded.",
            "dir": job_queue_dir,
            "poll_seconds": job_queue_poll_seconds,
        },
    }

    if inference_provider == "roboflow":
        startup_checks["model"].update(
            {
                "status": "ok" if roboflow_api_key_present else "warning",
                "message": (
                    "Roboflow hosted model is configured."
                    if roboflow_api_key_present
                    else "Roboflow provider selected but ROBOFLOW_API_KEY is missing."
                ),
                "provider": inference_provider,
                "path": roboflow_model_id,
            }
        )
    else:
        startup_checks["model"]["provider"] = inference_provider

    return RuntimeConfig(
        database_url=build_database_url(),
        inference_provider=inference_provider,
        model_path=model_path,
        roboflow_model_id=roboflow_model_id,
        roboflow_api_key_present=roboflow_api_key_present,
        yolo_confidence=_read_float("YOLO_CONFIDENCE", 0.35, minimum=0.01),
        yolo_imgsz=_read_int("YOLO_IMGSZ", 416, minimum=64),
        inference_every_n_frames=_read_int("INFERENCE_EVERY_N_FRAMES", 2, minimum=1),
        inference_min_interval_seconds=_read_float(
            "INFERENCE_MIN_INTERVAL_SECONDS", 0.35, minimum=0.05
        ),
        stream_fps=_read_float("STREAM_FPS", 12.0, minimum=1.0),
        camera_index=_read_int("CAMERA_INDEX", 0, minimum=0),
        camera_width=_read_int("CAMERA_WIDTH", 640, minimum=160),
        camera_height=_read_int("CAMERA_HEIGHT", 480, minimum=120),
        camera_backend=camera_backend,
        history_refresh_interval_seconds=_read_float(
            "HISTORY_REFRESH_INTERVAL_SECONDS", 2.0, minimum=0.2
        ),
        camera_retry_seconds=_read_float("CAMERA_RETRY_SECONDS", 1.0, minimum=0.2),
        video_analysis_frame_stride=_read_int(
            "VIDEO_ANALYSIS_FRAME_STRIDE", 3, minimum=1
        ),
        upload_dir=upload_dir,
        allowed_video_extensions=DEFAULT_ALLOWED_VIDEO_EXTENSIONS,
        allowed_image_extensions=DEFAULT_ALLOWED_IMAGE_EXTENSIONS,
        flask_secret_key=load_flask_secret_key(upload_dir=upload_dir),
        default_admin_password=os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123456"),
        max_upload_size_mb=max_upload_size_mb,
        max_upload_bytes=max_upload_size_mb * 1024 * 1024,
        job_executor_backend=job_executor_backend,
        job_executor_process_workers=job_executor_process_workers,
        job_queue_dir=job_queue_dir,
        job_queue_poll_seconds=job_queue_poll_seconds,
        startup_checks=startup_checks,
    )


def build_runtime_summary(config: RuntimeConfig) -> Dict[str, object]:
    return {
        "database_url": mask_database_url(config.database_url),
        "inference_provider": config.inference_provider,
        "model_path": config.model_path,
        "model_exists": os.path.exists(config.model_path),
        "roboflow_model_id": config.roboflow_model_id,
        "roboflow_api_key_present": config.roboflow_api_key_present,
        "yolo_confidence": config.yolo_confidence,
        "camera_index": config.camera_index,
        "camera_backend": config.camera_backend,
        "camera_resolution": "{}x{}".format(config.camera_width, config.camera_height),
        "stream_fps": config.stream_fps,
        "inference_every_n_frames": config.inference_every_n_frames,
        "inference_min_interval_seconds": config.inference_min_interval_seconds,
        "video_analysis_frame_stride": config.video_analysis_frame_stride,
        "upload_dir": config.upload_dir,
        "allowed_image_extensions": list(config.allowed_image_extensions),
        "max_upload_size_mb": config.max_upload_size_mb,
        "job_executor_backend": config.job_executor_backend,
        "job_executor_process_workers": config.job_executor_process_workers,
        "job_queue_dir": config.job_queue_dir,
        "job_queue_poll_seconds": config.job_queue_poll_seconds,
    }
