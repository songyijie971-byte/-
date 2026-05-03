import json
import logging
import os
import threading
import time
from datetime import datetime
from typing import Optional

from flask import Flask, g, jsonify, render_template, request, session, url_for
from sqlalchemy import text
from ultralytics import YOLO

from app_config import build_runtime_summary, load_runtime_config, mask_database_url
from app_core.context import create_app_context
from app_core.inference_runtime import inference_device_label
from app_core.registry import build_service_registry
from database import AlertEvent, AnalysisReport, SystemConfig, User, VideoAnalysisJob, build_database_url, session_scope
from focus_score import calculate_focus_score as _shared_calculate_focus_score
from security_service import CSRF_COOKIE_NAME, ensure_csrf_token

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
LOGGER = logging.getLogger(__name__)

RUNTIME_CONFIG = load_runtime_config()

app = Flask(__name__)
app.secret_key = RUNTIME_CONFIG.flask_secret_key
app.config["MAX_CONTENT_LENGTH"] = RUNTIME_CONFIG.max_upload_bytes


def _read_bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=_read_bool_env("SESSION_COOKIE_SECURE", False),
)


_NOISY_LOG_PATHS = {
    "/api/stats",
    "/api/dashboard_overview",
    "/api/analysis_status",
    "/api/my/uploads",
    "/api/history",
}


@app.before_request
def start_request_timer():
    g.request_started_at = time.perf_counter()


@app.after_request
def log_request_summary(response):
    try:
        if request.path.startswith("/static/") or request.path == "/video_feed":
            return response
        if request.path in _NOISY_LOG_PATHS and response.status_code < 400:
            return response

        started_at = getattr(g, "request_started_at", None)
        latency_ms = 0.0
        if started_at is not None:
            latency_ms = (time.perf_counter() - started_at) * 1000.0

        user_id = None
        current_user = getattr(g, "current_user", None)
        if current_user and isinstance(current_user, dict):
            user_id = current_user.get("id")
        if user_id is None:
            user_id = session.get("user_id")

        LOGGER.info(
            "HTTP %s %s status=%s latency_ms=%.1f user_id=%s",
            request.method,
            request.path,
            response.status_code,
            latency_ms,
            user_id,
        )
    except Exception:
        LOGGER.debug("Failed to log request summary", exc_info=True)
    return response


@app.after_request
def set_csrf_cookie(response):
    try:
        token = ensure_csrf_token(session)
        response.set_cookie(
            CSRF_COOKIE_NAME,
            token,
            httponly=False,
            samesite="Lax",
            secure=_read_bool_env("SESSION_COOKIE_SECURE", False),
        )
    except Exception:
        LOGGER.debug("Failed to set csrf cookie", exc_info=True)
    return response


def on_runtime_settings_updated(settings):
    app.config["MAX_CONTENT_LENGTH"] = int(settings["max_upload_size_mb"]) * 1024 * 1024


def _build_initial_camera_status():
    return {
        "status": "idle",
        "available": False,
        "message": "实时摄像头尚未启动，页面将优先展示占位画面。",
        "last_error": None,
        "last_frame_at": None,
        "placeholder_active": True,
        "camera_index": RUNTIME_CONFIG.camera_index,
        "camera_backend": RUNTIME_CONFIG.camera_backend,
    }


def _build_initial_model_state():
    model_exists = os.path.exists(RUNTIME_CONFIG.model_path)
    return {
        "status": "ready" if model_exists else "warning",
        "loaded": False,
        "message": (
            "模型文件已就绪，首次推理时会自动加载。"
            if model_exists
            else "未检测到模型文件，相关接口会返回明确错误。"
        ),
        "path": RUNTIME_CONFIG.model_path,
        "device": inference_device_label(),
        "last_error": None,
    }


APP_CONTEXT = create_app_context(
    runtime_config=RUNTIME_CONFIG,
    logger=LOGGER,
    initial_camera_status_factory=_build_initial_camera_status,
    initial_model_state_factory=_build_initial_model_state,
)
app.extensions["classroom_demo.context"] = APP_CONTEXT


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


def calculate_focus_score(stable_counts: dict) -> dict:
    penalties = (
        stable_counts.get("low_head", 0) * 12
        + stable_counts.get("sleep", 0) * 20
        + stable_counts.get("turn_talk", 0) * 15
    )
    rewards = stable_counts.get("hand_raise", 0) * 4
    score = max(0, min(100, 100 - penalties + rewards))

    if score >= 80:
        level = "高"
        summary_text = "当前课堂整体专注度较高，课堂状态较为稳定。"
    elif score >= 60:
        level = "中"
        summary_text = "当前课堂专注度处于中等区间，建议关注波动学生。"
    else:
        level = "低"
        summary_text = "当前课堂专注度偏低，建议及时进行干预。"

    return {
        "score": score,
        "level": level,
        "summary_text": summary_text,
        "rule_text": "100 - 低头×12 - 睡觉×20 - 转头交谈×15 + 举手×4",
        "limits_text": "该评分仅用于课堂状态可视化展示，不直接等同于教学质量评价。",
    }


# Rebind these helpers so every caller shares the same scoring semantics and
# model initialization is synchronized across request and worker threads.
def get_model():
    if APP_CONTEXT.model is not None:
        return APP_CONTEXT.model

    with APP_CONTEXT.model_lock:
        if APP_CONTEXT.model is not None:
            return APP_CONTEXT.model

        if not os.path.exists(RUNTIME_CONFIG.model_path):
            with APP_CONTEXT.runtime_lock:
                APP_CONTEXT.runtime_refs["model_state"].update(
                    {
                        "status": "error",
                        "loaded": False,
                        "message": "未找到模型文件，请检查 YOLO_MODEL_PATH 配置。",
                        "last_error": "missing_model_file",
                    }
                )
            raise FileNotFoundError(
                "未找到模型文件，请检查 YOLO_MODEL_PATH 配置: {}".format(
                    RUNTIME_CONFIG.model_path
                )
            )

        try:
            APP_CONTEXT.model = YOLO(RUNTIME_CONFIG.model_path, task="detect")
            with APP_CONTEXT.runtime_lock:
                APP_CONTEXT.runtime_refs["model_state"].update(
                    {
                        "status": "ok",
                        "loaded": True,
                        "device": inference_device_label(),
                        "message": "模型已加载，可用于实时监测与视频分析。",
                        "last_error": None,
                    }
                )
            return APP_CONTEXT.model
        except Exception as exc:
            with APP_CONTEXT.runtime_lock:
                APP_CONTEXT.runtime_refs["model_state"].update(
                    {
                        "status": "error",
                        "loaded": False,
                        "message": "模型加载失败，请检查文件格式与推理环境。",
                        "last_error": str(exc),
                    }
                )
            raise


def calculate_focus_score(stable_counts: dict) -> dict:
    return _shared_calculate_focus_score(stable_counts)


def build_health_payload():
    database_status = {
        "status": "ok",
        "message": "数据库连接正常。",
        "url": mask_database_url(RUNTIME_CONFIG.database_url),
    }
    try:
        with APP_CONTEXT.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        LOGGER.exception("Database health check failed")
        database_status.update(
            {"status": "error", "message": "数据库连接失败。", "error": str(exc)}
        )

    upload_dir_exists = os.path.isdir(RUNTIME_CONFIG.upload_dir)
    upload_dir_writable = upload_dir_exists and os.access(RUNTIME_CONFIG.upload_dir, os.W_OK)
    storage_status = {
        "status": "ok" if upload_dir_exists and upload_dir_writable else "error",
        "message": (
            "上传目录可读可写。"
            if upload_dir_exists and upload_dir_writable
            else "上传目录不可用，请检查 UPLOAD_DIR 路径与权限。"
        ),
        "path": RUNTIME_CONFIG.upload_dir,
        "writable": upload_dir_writable,
    }

    with APP_CONTEXT.runtime_lock: model_status = dict(APP_CONTEXT.runtime_refs["model_state"])
    model_status["exists"] = os.path.exists(RUNTIME_CONFIG.model_path)

    with APP_CONTEXT.runtime_lock: fallback_camera_status = dict(APP_CONTEXT.runtime_refs["camera_status"])
    with APP_CONTEXT.stats_lock:
        camera_status = dict(
            APP_CONTEXT.current_stats.get("camera_status")
            or fallback_camera_status
        )

    job_queue_dir = RUNTIME_CONFIG.job_queue_dir
    job_queue_dirs = {
        "pending": os.path.join(job_queue_dir, "pending"),
        "processing": os.path.join(job_queue_dir, "processing"),
        "done": os.path.join(job_queue_dir, "done"),
        "failed": os.path.join(job_queue_dir, "failed"),
    }

    def _count_queue(dir_path: str) -> int:
        try:
            return len([name for name in os.listdir(dir_path) if name.endswith(".json")])
        except FileNotFoundError:
            return 0
        except OSError:
            return 0

    job_queue_status = {
        "backend": RUNTIME_CONFIG.job_executor_backend,
        "dir": job_queue_dir,
        "pending": _count_queue(job_queue_dirs["pending"]),
        "processing": _count_queue(job_queue_dirs["processing"]),
        "done": _count_queue(job_queue_dirs["done"]),
        "failed": _count_queue(job_queue_dirs["failed"]),
    }

    recent_analysis = None
    try:
        with session_scope(APP_CONTEXT.session_factory) as db:
            job = (
                db.query(VideoAnalysisJob)
                .filter(VideoAnalysisJob.status.in_(("completed", "failed")))
                .order_by(VideoAnalysisJob.finished_at.desc(), VideoAnalysisJob.id.desc())
                .first()
            )
            if job is not None:
                metrics = {}
                if job.status == "completed" and bool(job.report_ready):
                    report = (
                        db.query(AnalysisReport)
                        .filter(
                            AnalysisReport.job_id == job.job_id,
                            AnalysisReport.user_id == job.user_id,
                        )
                        .one_or_none()
                    )
                    if report is not None:
                        metrics = _json_loads(getattr(report, "analysis_metrics_json", ""), {})
                recent_analysis = {
                    "status": job.status,
                    "finished_at": _format_dt(getattr(job, "finished_at", None)),
                    "analysis_metrics": metrics,
                }
    except Exception:
        LOGGER.debug("Failed to load recent analysis metrics", exc_info=True)

    statuses = [database_status["status"], storage_status["status"], model_status["status"]]
    overall_status = "ok"
    if any(status == "error" for status in statuses):
        overall_status = "error"
    elif any(
        status in {"warning", "degraded"}
        for status in statuses + [camera_status["status"]]
    ):
        overall_status = "degraded"

    message_map = {
        "ok": "系统运行正常，可以进行实时监测、上传分析和报告查看。",
        "degraded": "系统可用，但存在降级项，请关注健康详情。",
        "error": "系统存在关键异常，请根据健康详情先处理环境问题。",
    }

    return {
        "ok": overall_status != "error",
        "status": overall_status,
        "message": message_map[overall_status],
        "checked_at": _format_dt(datetime.now()),
        "runtime": build_runtime_summary(RUNTIME_CONFIG),
        "database": database_status,
        "model": model_status,
        "camera": camera_status,
        "storage": storage_status,
        "job_queue": job_queue_status,
        "recent_analysis": recent_analysis,
        "startup_checks": RUNTIME_CONFIG.startup_checks,
    }


def _status_page_context(title, message, status_code, action_href=None, action_label=None):
    return {
        "title": title,
        "message": message,
        "status_code": status_code,
        "action_href": action_href,
        "action_label": action_label,
    }


@app.errorhandler(403)
def handle_forbidden(error):
    message = "当前账号无权访问该页面或资源。"
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "message": message}), 403
    return (
        render_template(
            "status_page.html",
            **_status_page_context(
                "无权限访问",
                message,
                403,
                action_href=url_for("login_page"),
                action_label="返回登录页",
            ),
        ),
        403,
    )


@app.errorhandler(404)
def handle_not_found(error):
    message = "未找到对应页面或资源，请检查访问路径是否正确。"
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "message": message}), 404
    action_href = url_for("dashboard_page") if session.get("user_id") else url_for("login_page")
    action_label = "返回系统首页" if session.get("user_id") else "返回登录页"
    return (
        render_template(
            "status_page.html",
            **_status_page_context(
                "页面不存在",
                message,
                404,
                action_href=action_href,
                action_label=action_label,
            ),
        ),
        404,
    )


@app.errorhandler(413)
def handle_payload_too_large(error):
    message = "上传文件过大，请控制在 {} MB 以内。".format(
        RUNTIME_CONFIG.max_upload_size_mb
    )
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "message": message}), 413
    return (
        render_template(
            "status_page.html",
            **_status_page_context(
                "文件过大",
                message,
                413,
                action_href=url_for("analysis_page"),
                action_label="返回上传分析",
            ),
        ),
        413,
    )


LOGGER.info(
    "Runtime config summary: %s",
    json.dumps(build_runtime_summary(RUNTIME_CONFIG), ensure_ascii=False),
)

DEPENDENCIES = build_service_registry(
    app,
    APP_CONTEXT,
    {
        "LOGGER": LOGGER,
        "build_health_payload": build_health_payload,
        "calculate_focus_score": calculate_focus_score,
        "get_model": get_model,
        "on_runtime_settings_updated": on_runtime_settings_updated,
        "_format_dt": _format_dt,
        "_format_timestamp": _format_timestamp,
        "_json_dumps": _json_dumps,
        "_json_loads": _json_loads,
    },
)
app.extensions["classroom_demo.dependencies"] = DEPENDENCIES
DEPENDENCIES["reset_runtime_stats"]()


def create_app():
    return app

# Compatibility exports used by tests and legacy integration code.
engine = APP_CONTEXT.engine
SessionFactory = APP_CONTEXT.session_factory
frame_lock = APP_CONTEXT.frame_lock
runtime_refs = APP_CONTEXT.runtime_refs
MAX_UPLOAD_BYTES = RUNTIME_CONFIG.max_upload_bytes
get_display_frame = DEPENDENCIES["get_display_frame"]
