from flask import abort, g, redirect, render_template, send_from_directory, url_for


def register_report_routes(app, deps):
    login_required_page = deps["login_required_page"]
    SessionFactory = deps["SessionFactory"]
    session_scope = deps["session_scope"]
    build_report_payload = deps["build_report_payload"]
    _format_dt = deps["_format_dt"]
    event_storage = deps["event_storage"]
    UPLOAD_DIR = deps["UPLOAD_DIR"]
    get_latest_reportable_job_for_user = deps["get_latest_reportable_job_for_user"]
    get_accessible_job_by_id = deps["get_accessible_job_by_id"]
    get_accessible_job_by_filename = deps["get_accessible_job_by_filename"]
    get_accessible_snapshot_event = deps["get_accessible_snapshot_event"]
    get_report_for_job_and_user = deps["get_report_for_job_and_user"]

    @app.route("/report/latest")
    @login_required_page
    def latest_report():
        with session_scope(SessionFactory) as db:
            job = get_latest_reportable_job_for_user(db, g.current_user)
            if job is None:
                return render_template("report.html", report=None, generated_at_label="--")
            return redirect(url_for("report_page", job_id=job.job_id))

    @app.route("/report/<job_id>")
    @login_required_page
    def report_page(job_id):
        with session_scope(SessionFactory) as db:
            job = get_accessible_job_by_id(db, g.current_user, job_id)
            if job is None:
                abort(404)

            report = get_report_for_job_and_user(db, job.job_id, job.user_id)
            if report is None:
                return render_template("report.html", report=None, generated_at_label="--")

            events = event_storage.list_events(limit=500, user_id=job.user_id, job_id=job.job_id)
            payload = build_report_payload(job, report, events)
            return render_template(
                "report.html",
                report=payload,
                generated_at_label=_format_dt(report.generated_at),
            )

    @app.route("/uploads/<path:filename>")
    @login_required_page
    def uploaded_file(filename):
        with session_scope(SessionFactory) as db:
            job = get_accessible_job_by_filename(db, g.current_user, filename)
            if job is None:
                abort(404)
        return send_from_directory(UPLOAD_DIR, filename)

    @app.route("/snapshots/<path:filename>")
    @login_required_page
    def snapshot_file(filename):
        snapshot_path = "/snapshots/{}".format(filename)
        with session_scope(SessionFactory) as db:
            event = get_accessible_snapshot_event(db, g.current_user, snapshot_path)
            if event is None:
                abort(404)
        return send_from_directory(event_storage.snapshot_dir, filename)
