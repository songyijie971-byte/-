"""Repository helpers that isolate ORM query details from services and routes."""


def build_repository_helpers(deps):
    User = deps["User"]
    VideoAnalysisJob = deps["VideoAnalysisJob"]
    AnalysisReport = deps["AnalysisReport"]
    AlertEvent = deps["AlertEvent"]
    ROLE_ADMIN = deps["ROLE_ADMIN"]
    ROLE_TEACHER = deps["ROLE_TEACHER"]
    or_ = deps["or_"]

    def get_active_user(db, user_id):
        return (
            db.query(User)
            .filter(User.id == user_id, User.is_active.is_(True))
            .one_or_none()
        )

    def get_user_by_account(db, account):
        return (
            db.query(User)
            .filter(or_(User.username == account, User.email == account.lower()))
            .one_or_none()
        )

    def has_admin_user(db):
        return db.query(User.id).filter(User.role == ROLE_ADMIN).first() is not None

    def get_duplicate_user(db, username, email):
        return (
            db.query(User.id)
            .filter(or_(User.username == username, User.email == email))
            .first()
        )

    def create_user_record(db, **fields):
        user = User(**fields)
        db.add(user)
        db.flush()
        return user

    def query_jobs_for_user(db, user):
        return db.query(VideoAnalysisJob).filter(VideoAnalysisJob.user_id == user["id"])

    def get_latest_job_for_user(db, user):
        return (
            query_jobs_for_user(db, user)
            .filter(VideoAnalysisJob.status != "deleted")
            .order_by(VideoAnalysisJob.created_at.desc(), VideoAnalysisJob.id.desc())
            .first()
        )

    def get_visible_job(db, user, job_id, include_deleted=False):
        query = query_jobs_for_user(db, user).filter(VideoAnalysisJob.job_id == job_id)
        if not include_deleted:
            query = query.filter(VideoAnalysisJob.status != "deleted")
        return query.one_or_none()

    def get_job_by_id(db, job_id):
        return (
            db.query(VideoAnalysisJob)
            .filter(VideoAnalysisJob.job_id == job_id)
            .one_or_none()
        )

    def create_upload_job_record(db, **fields):
        job = VideoAnalysisJob(**fields)
        db.add(job)
        db.flush()
        return job

    def delete_job_artifacts(db, job_id, user_id):
        db.query(AnalysisReport).filter(
            AnalysisReport.job_id == job_id,
            AnalysisReport.user_id == user_id,
        ).delete(synchronize_session=False)
        db.query(AlertEvent).filter(
            AlertEvent.job_id == job_id,
            AlertEvent.user_id == user_id,
        ).delete(synchronize_session=False)

    def get_report_for_job_and_user(db, job_id, user_id):
        return (
            db.query(AnalysisReport)
            .filter(AnalysisReport.job_id == job_id, AnalysisReport.user_id == user_id)
            .one_or_none()
        )

    def get_or_create_report(db, job_id, user_id):
        report = get_report_for_job_and_user(db, job_id, user_id)
        if report is None:
            report = AnalysisReport(job_id=job_id, user_id=user_id)
            db.add(report)
        return report

    def get_latest_reportable_job_for_user(db, user):
        return (
            query_jobs_for_user(db, user)
            .filter(
                VideoAnalysisJob.status != "deleted",
                VideoAnalysisJob.report_ready.is_(True),
            )
            .order_by(VideoAnalysisJob.updated_at.desc(), VideoAnalysisJob.id.desc())
            .first()
        )

    def count_jobs_for_user_by_status(db, user, statuses):
        return query_jobs_for_user(db, user).filter(VideoAnalysisJob.status.in_(statuses)).count()

    def count_completed_reports_for_user(db, user):
        return (
            query_jobs_for_user(db, user)
            .filter(
                VideoAnalysisJob.status != "deleted",
                VideoAnalysisJob.report_ready.is_(True),
            )
            .count()
        )

    def get_accessible_job_by_id(db, current_user, job_id):
        query = db.query(VideoAnalysisJob).filter(
            VideoAnalysisJob.job_id == job_id,
            VideoAnalysisJob.status != "deleted",
        )
        if current_user["role"] != ROLE_ADMIN:
            query = query.filter(VideoAnalysisJob.user_id == current_user["id"])
        return query.one_or_none()

    def get_accessible_job_by_filename(db, current_user, filename):
        query = db.query(VideoAnalysisJob).filter(
            VideoAnalysisJob.stored_filename == filename,
            VideoAnalysisJob.status != "deleted",
        )
        if current_user["role"] != ROLE_ADMIN:
            query = query.filter(VideoAnalysisJob.user_id == current_user["id"])
        return query.one_or_none()

    def get_accessible_snapshot_event(db, current_user, snapshot_path):
        query = db.query(AlertEvent).filter(AlertEvent.snapshot_path == snapshot_path)
        if current_user["role"] == ROLE_ADMIN:
            return query.order_by(AlertEvent.id.desc()).first()
        if current_user["role"] == ROLE_TEACHER:
            return (
                query.filter(
                    or_(
                        AlertEvent.user_id == current_user["id"],
                        AlertEvent.user_id.is_(None),
                    )
                )
                .order_by(AlertEvent.id.desc())
                .first()
            )
        return (
            query.filter(AlertEvent.user_id == current_user["id"])
            .order_by(AlertEvent.id.desc())
            .first()
        )

    return {
        "count_completed_reports_for_user": count_completed_reports_for_user,
        "count_jobs_for_user_by_status": count_jobs_for_user_by_status,
        "create_upload_job_record": create_upload_job_record,
        "create_user_record": create_user_record,
        "delete_job_artifacts": delete_job_artifacts,
        "get_accessible_job_by_filename": get_accessible_job_by_filename,
        "get_accessible_job_by_id": get_accessible_job_by_id,
        "get_accessible_snapshot_event": get_accessible_snapshot_event,
        "get_active_user": get_active_user,
        "get_duplicate_user": get_duplicate_user,
        "get_job_by_id": get_job_by_id,
        "get_latest_job_for_user": get_latest_job_for_user,
        "get_latest_reportable_job_for_user": get_latest_reportable_job_for_user,
        "get_or_create_report": get_or_create_report,
        "get_report_for_job_and_user": get_report_for_job_and_user,
        "get_user_by_account": get_user_by_account,
        "get_visible_job": get_visible_job,
        "has_admin_user": has_admin_user,
        "query_jobs_for_user": query_jobs_for_user,
    }

