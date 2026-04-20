from app_core.analysis_workflow import (
    AnalysisReportBuilders,
    AnalysisRepositories,
    AnalysisRuntimeContext,
    UploadAnalysisApplicationService,
)
from app_core.job_executor import UploadAnalysisTask


def create_upload_analysis_service(deps) -> UploadAnalysisApplicationService:
    runtime = AnalysisRuntimeContext(
        behavior_display_names=deps["BEHAVIOR_DISPLAY_NAMES"],
        session_factory=deps["SessionFactory"],
        session_scope=deps["session_scope"],
        load_behavior_rules=deps["load_behavior_rules"],
        event_storage=deps["event_storage"],
        get_model=deps["get_model"],
        normalize_detections=deps["normalize_detections"],
        map_detections_to_behaviors=deps["map_detections_to_behaviors"],
        save_alert_snapshot=deps["save_alert_snapshot"],
        calculate_focus_score=deps["calculate_focus_score"],
        user_can_access_camera=deps["user_can_access_camera"],
        json_dumps=deps["_json_dumps"],
        json_loads=deps["_json_loads"],
        format_timestamp=deps["_format_timestamp"],
        format_datetime=deps["_format_dt"],
        allowed_video_extensions=deps["ALLOWED_VIDEO_EXTENSIONS"],
        logger=deps["LOGGER"],
        cv2=deps["cv2"],
        stats_lock=deps["stats_lock"],
        current_stats=deps["current_stats"],
        source_lock=deps["source_lock"],
        source_state=deps["source_state"],
        get_behavior_rule_config_payload=deps["get_behavior_rule_config_payload"],
        get_runtime_setting=deps["get_runtime_setting"],
    )
    repositories = AnalysisRepositories(
        query_jobs_for_user=deps["query_jobs_for_user"],
        get_latest_job_for_user=deps["get_latest_job_for_user"],
        get_visible_job=deps["get_visible_job"],
        get_job_by_id=deps["get_job_by_id"],
        create_upload_job_record=deps["create_upload_job_record"],
        delete_job_artifacts=deps["delete_job_artifacts"],
        get_or_create_report=deps["get_or_create_report"],
        get_report_for_job_and_user=deps["get_report_for_job_and_user"],
        get_latest_reportable_job_for_user=deps["get_latest_reportable_job_for_user"],
        count_jobs_for_user_by_status=deps["count_jobs_for_user_by_status"],
        count_completed_reports_for_user=deps["count_completed_reports_for_user"],
    )
    report_builders = AnalysisReportBuilders(
        build_behavior_report_rows=deps["build_behavior_report_rows"],
        build_report_insights=deps["build_report_insights"],
        build_risk_assessment=deps["build_risk_assessment"],
        build_teacher_suggestions=deps["build_teacher_suggestions"],
        build_report_gallery=deps["build_report_gallery"],
        build_rule_snapshot_for_report=deps["build_rule_snapshot_for_report"],
        build_analysis_metrics=deps["build_analysis_metrics"],
        serialize_job=deps["serialize_job"],
        job_status_message=deps["job_status_message"],
    )

    return UploadAnalysisApplicationService(
        runtime=runtime,
        repositories=repositories,
        report_builders=report_builders,
        temporal_analyzer_factory=deps["BehaviorTemporalAnalyzer"],
    )


def build_analysis_services(deps):
    service = create_upload_analysis_service(deps)

    def handle_upload_analysis_task(task: UploadAnalysisTask) -> None:
        service.process_uploaded_video(task.job_id, task.user_id, task.file_path)

    return {
        "analysis_application_service": service,
        "handle_upload_analysis_task": handle_upload_analysis_task,
        "empty_analysis_status": service.empty_analysis_status,
        "allowed_video_file": service.allowed_video_file,
        "query_jobs_for_user": service.query_jobs_for_user,
        "get_latest_job_for_user": service.get_latest_job_for_user,
        "get_visible_job": service.get_visible_job,
        "update_job_record": service.update_job_record,
        "purge_job_artifacts": service.purge_job_artifacts,
        "is_job_deleted": service.is_job_deleted,
        "save_report_record": service.save_report_record,
        "create_upload_job": service.create_upload_job,
        "analyze_uploaded_results": service.analyze_uploaded_results,
        "process_uploaded_video": service.process_uploaded_video,
        "build_analysis_status_for_user": service.build_analysis_status_for_user,
        "build_history_response_for_user": service.build_history_response_for_user,
        "build_stats_response": service.build_stats_response,
        "build_dashboard_payload": service.build_dashboard_payload,
    }
