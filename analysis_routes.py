import os
import uuid
from datetime import datetime

from flask import Response, abort, g, jsonify, redirect, render_template, request, send_from_directory, url_for
from werkzeug.utils import secure_filename

from app_core.fs_utils import delete_files, list_files_with_prefix, safe_delete_file
from app_core.job_executor import UploadAnalysisTask


def register_analysis_routes(app, deps):
    camera_required_page = deps["camera_required_page"]
    login_required_page = deps["login_required_page"]
    camera_required_stream = deps["camera_required_stream"]
    camera_required_api = deps["camera_required_api"]
    login_required_api = deps["login_required_api"]
    build_stats_response = deps["build_stats_response"]
    build_history_response_for_user = deps["build_history_response_for_user"]
    build_analysis_status_for_user = deps["build_analysis_status_for_user"]
    build_dashboard_payload = deps["build_dashboard_payload"]
    refresh_public_history_cache_if_needed = deps["refresh_public_history_cache_if_needed"]
    generate_frames = deps["generate_frames"]
    allowed_image_file = deps["allowed_image_file"]
    allowed_video_file = deps["allowed_video_file"]
    analyze_uploaded_image = deps["analyze_uploaded_image"]
    create_upload_job = deps["create_upload_job"]
    upload_analysis_dispatcher = deps["upload_analysis_dispatcher"]
    SessionFactory = deps["SessionFactory"]
    session_scope = deps["session_scope"]
    VideoAnalysisJob = deps["VideoAnalysisJob"]
    UPLOAD_DIR = deps["UPLOAD_DIR"]
    get_runtime_setting = deps["get_runtime_setting"]
    query_jobs_for_user = deps["query_jobs_for_user"]
    get_visible_job = deps["get_visible_job"]
    get_job_by_id = deps["get_job_by_id"]
    serialize_job = deps["serialize_job"]
    job_status_message = deps["job_status_message"]
    purge_job_artifacts = deps["purge_job_artifacts"]
    event_storage = deps["event_storage"]
    LOGGER = deps["LOGGER"]
    csrf_protect_api = deps["csrf_protect_api"]
    runtime_lock = deps["runtime_lock"]
    runtime_refs = deps["runtime_refs"]

    def _normalize_relative_upload_path(path: str) -> str:
        normalized = os.path.normpath(path or "").replace("\\", "/").lstrip("/")
        if not normalized or normalized.startswith("../") or normalized == "..":
            abort(404)
        return normalized

    def _safe_upload_abspath(relative_path: str) -> str:
        upload_root = os.path.abspath(UPLOAD_DIR)
        absolute_path = os.path.abspath(os.path.join(upload_root, relative_path))
        if absolute_path != upload_root and not absolute_path.startswith(upload_root + os.sep):
            abort(404)
        return absolute_path

    def _user_image_prefix(user_id: int) -> str:
        return "images/user_{}/".format(user_id)

    def _get_latest_image_analysis(user_id: int):
        with runtime_lock:
            records = runtime_refs.setdefault("image_analysis_records_by_user", {})
            user_records = list(records.get(user_id, []))
        return user_records[0] if user_records else None

    def _store_image_analysis(user_id: int, payload: dict):
        with runtime_lock:
            records = runtime_refs.setdefault("image_analysis_records_by_user", {})
            user_records = list(records.get(user_id, []))
            user_records.insert(0, payload)
            stale_records = user_records[6:]
            records[user_id] = user_records[:6]

        upload_root = os.path.abspath(UPLOAD_DIR)
        for item in stale_records:
            for key in ("source_relative_path", "annotated_relative_path"):
                relative_path = item.get(key)
                if not relative_path:
                    continue
                safe_delete_file(
                    os.path.join(upload_root, relative_path),
                    allowed_base_dir=upload_root,
                    logger=LOGGER,
                )

    def _measure_file_size(uploaded_file):
        stream = uploaded_file.stream
        current_position = stream.tell()
        stream.seek(0, os.SEEK_END)
        size_bytes = stream.tell()
        stream.seek(current_position, os.SEEK_SET)
        return size_bytes

    def max_upload_bytes():
        size_mb = max(1, int(get_runtime_setting("max_upload_size_mb") or 1))
        return size_mb * 1024 * 1024

    @app.route("/")
    @camera_required_page
    def index():
        return render_template("dashboard.html", active_page="dashboard")

    @app.route("/dashboard")
    @camera_required_page
    def dashboard_page():
        return render_template("dashboard.html", active_page="dashboard")

    @app.route("/monitor")
    @camera_required_page
    def monitor_page():
        return render_template("monitor.html", active_page="monitor")

    @app.route("/history-view")
    @login_required_page
    def history_page():
        return render_template("history.html", active_page="history")

    @app.route("/analysis-view")
    @login_required_page
    def analysis_page():
        return render_template("analysis.html", active_page="analysis")

    @app.route("/legacy/index")
    @camera_required_page
    def legacy_index():
        return redirect(url_for("dashboard_page"))

    @app.route("/my/uploads")
    @login_required_page
    def my_uploads_page():
        reason = request.args.get("reason")
        if reason == "no_camera_permission":
            return redirect(url_for("analysis_page", notice="no_camera_permission"))
        return redirect(url_for("analysis_page"))

    @app.route("/video_feed")
    @camera_required_stream
    def video_feed():
        return Response(
            generate_frames(),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    @app.route("/api/stats")
    @camera_required_api
    def api_stats():
        return jsonify(build_stats_response())

    @app.route("/api/dashboard_overview")
    @camera_required_api
    def api_dashboard_overview():
        return jsonify(build_dashboard_payload(g.current_user))

    @app.route("/api/history")
    @login_required_api
    def api_history():
        return jsonify(build_history_response_for_user(g.current_user))

    @app.route("/api/analysis_status")
    @login_required_api
    def api_analysis_status():
        job_id = request.args.get("job_id")
        payload = build_analysis_status_for_user(g.current_user, job_id=job_id)
        if job_id and not payload.get("job_id"):
            return jsonify({"ok": False, "message": "任务不存在"}), 404
        return jsonify(payload)

    @app.route("/api/source/camera", methods=["POST"])
    @camera_required_api
    @csrf_protect_api
    def api_source_camera():
        refresh_public_history_cache_if_needed(force=True)
        payload = build_stats_response()
        camera_status = payload.get("camera_status", {})
        return jsonify(
            {
                "ok": True,
                "message": camera_status.get("message", "已切回实时摄像头模式。"),
                "camera_status": camera_status,
            }
        )

    @app.route("/api/upload_video", methods=["POST"])
    @login_required_api
    @csrf_protect_api
    def api_upload_video():
        file = request.files.get("video")
        if file is None or not file.filename:
            return jsonify({"ok": False, "message": "请选择视频文件"}), 400

        original_name = file.filename
        filename = secure_filename(original_name)
        if not filename:
            _, ext = os.path.splitext(original_name)
            filename = "upload{}".format(ext.lower())
        if not allowed_video_file(filename):
            return jsonify({"ok": False, "message": "仅支持 mp4 / avi / mov / mkv / webm"}), 400

        size_bytes = _measure_file_size(file)
        if size_bytes <= 0:
            return jsonify({"ok": False, "message": "上传文件为空，请重新选择视频。"}), 400

        current_max_upload_bytes = max_upload_bytes()
        if size_bytes > current_max_upload_bytes:
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": "上传文件过大，请控制在 {} MB 以内。".format(
                            round(current_max_upload_bytes / 1024 / 1024)
                        ),
                    }
                ),
                413,
            )

        preview_job_id = uuid.uuid4().hex
        stored_name = "{}_{}".format(preview_job_id, filename)
        file_path = os.path.join(UPLOAD_DIR, stored_name)
        file.save(file_path)

        job_id = create_upload_job(
            user_id=g.current_user["id"],
            original_filename=original_name,
            stored_filename=stored_name,
            source_path=file_path,
            source_size_bytes=size_bytes,
        )

        with session_scope(SessionFactory) as db:
            job = get_job_by_id(db, job_id)
            actual_stored_name = "{}_{}".format(job_id, filename)
            actual_path = os.path.join(UPLOAD_DIR, actual_stored_name)
            if actual_stored_name != stored_name:
                os.replace(file_path, actual_path)
                job.stored_filename = actual_stored_name
                job.source_path = actual_path
                stored_name = actual_stored_name
                file_path = actual_path
            else:
                job.source_path = file_path

        submission = upload_analysis_dispatcher.dispatch(
            UploadAnalysisTask(
                job_id=job_id,
                user_id=g.current_user["id"],
                file_path=file_path,
            )
        )

        return jsonify(
            {
                "ok": True,
                "message": "视频已上传，分析任务已创建。",
                "job_id": job_id,
                "source_url": "/uploads/{}".format(stored_name),
                "job_backend": submission.backend,
            }
        )

    @app.route("/api/analyze_image", methods=["POST"])
    @login_required_api
    @csrf_protect_api
    def api_analyze_image():
        file = request.files.get("image")
        if file is None or not file.filename:
            return jsonify({"ok": False, "message": "请选择图片文件"}), 400

        original_name = file.filename
        filename = secure_filename(original_name)
        if not filename:
            _, ext = os.path.splitext(original_name)
            filename = "image{}".format(ext.lower())
        if not allowed_image_file(filename):
            return jsonify({"ok": False, "message": "仅支持 jpg / jpeg / png / bmp / webp"}), 400

        size_bytes = _measure_file_size(file)
        if size_bytes <= 0:
            return jsonify({"ok": False, "message": "上传图片为空，请重新选择文件。"}), 400

        current_max_upload_bytes = max_upload_bytes()
        if size_bytes > current_max_upload_bytes:
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": "上传文件过大，请控制在 {} MB 以内。".format(
                            round(current_max_upload_bytes / 1024 / 1024)
                        ),
                    }
                ),
                413,
            )

        image_dir = os.path.join(
            UPLOAD_DIR,
            "images",
            "user_{}".format(g.current_user["id"]),
        )
        os.makedirs(image_dir, exist_ok=True)
        stored_name = "{}_{}".format(uuid.uuid4().hex, filename)
        file_path = os.path.join(image_dir, stored_name)
        file.save(file_path)

        relative_source_path = os.path.relpath(file_path, UPLOAD_DIR).replace("\\", "/")
        try:
            payload = analyze_uploaded_image(
                file_path=file_path,
                original_filename=original_name,
                source_relative_path=relative_source_path,
                source_size_bytes=size_bytes,
            )
        except Exception:
            safe_delete_file(
                file_path,
                allowed_base_dir=os.path.abspath(UPLOAD_DIR),
                logger=LOGGER,
            )
            raise

        _store_image_analysis(g.current_user["id"], payload)
        return jsonify(dict(payload, ok=True, available=True))

    @app.route("/api/image_analysis/latest")
    @login_required_api
    def api_latest_image_analysis():
        payload = _get_latest_image_analysis(g.current_user["id"])
        if payload is None:
            return jsonify(
                {
                    "ok": True,
                    "available": False,
                    "message": "暂无图片分析结果",
                    "source_mode": "image",
                    "source_label": "上传图片",
                }
            )
        return jsonify(dict(payload, ok=True, available=True))

    @app.route("/image-uploads/<path:filename>")
    @login_required_page
    def uploaded_image_file(filename):
        relative_path = _normalize_relative_upload_path(filename)
        if g.current_user["role"] != "admin":
            if not relative_path.startswith(_user_image_prefix(g.current_user["id"])):
                abort(404)
        absolute_path = _safe_upload_abspath(relative_path)
        if not os.path.exists(absolute_path):
            abort(404)
        return send_from_directory(UPLOAD_DIR, relative_path)

    @app.route("/api/my/uploads")
    @login_required_api
    def api_my_uploads():
        with session_scope(SessionFactory) as db:
            jobs = (
                query_jobs_for_user(db, g.current_user)
                .filter(
                    VideoAnalysisJob.status != "deleted"
                )
                .order_by(
                    VideoAnalysisJob.created_at.desc(),
                    VideoAnalysisJob.id.desc(),
                )
                .all()
            )
            return jsonify({"items": [serialize_job(job) for job in jobs]})

    @app.route("/api/my/uploads/<job_id>")
    @login_required_api
    def api_my_upload_detail(job_id):
        with session_scope(SessionFactory) as db:
            job = get_visible_job(db, g.current_user, job_id)
            if job is None:
                return jsonify({"ok": False, "message": "任务不存在"}), 404
            payload = serialize_job(job)
            payload["message"] = job_status_message(job)
            return jsonify(payload)

    @app.route("/api/my/uploads/<job_id>", methods=["DELETE"])
    @login_required_api
    @csrf_protect_api
    def api_my_upload_delete(job_id):
        upload_dir = os.path.abspath(UPLOAD_DIR)
        snapshot_dir = os.path.abspath(event_storage.snapshot_dir)
        source_path = None
        stored_name = None
        with session_scope(SessionFactory) as db:
            job = get_visible_job(db, g.current_user, job_id, include_deleted=True)
            if job is None:
                return jsonify({"ok": False, "message": "任务不存在"}), 404
            if job.status == "deleted":
                return jsonify({"ok": True, "message": "该任务已删除。"}), 200

            source_path = getattr(job, "source_path", None)
            stored_name = getattr(job, "stored_filename", None)
            job.status = "deleted"
            job.report_ready = False
            job.progress = 0.0
            job.status_detail = "任务已删除，后台线程会自动停止处理。"
            job.deleted_at = datetime.utcnow()

        deleted_files = 0
        if source_path:
            deleted_files += int(
                safe_delete_file(source_path, allowed_base_dir=upload_dir, logger=LOGGER)
            )
        if stored_name:
            deleted_files += int(
                safe_delete_file(
                    os.path.join(upload_dir, stored_name),
                    allowed_base_dir=upload_dir,
                    logger=LOGGER,
                )
            )

        deleted_files += delete_files(
            list_files_with_prefix(upload_dir, "{}_".format(job_id)),
            allowed_base_dir=upload_dir,
            logger=LOGGER,
        )
        deleted_files += delete_files(
            list_files_with_prefix(snapshot_dir, "{}_".format(job_id[:8])),
            allowed_base_dir=snapshot_dir,
            logger=LOGGER,
        )

        purge_job_artifacts(job_id, g.current_user["id"])
        return jsonify(
            {"ok": True, "message": "任务已删除。", "deleted_files": deleted_files}
        )
