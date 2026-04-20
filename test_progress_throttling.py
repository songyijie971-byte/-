import logging
import os
import shutil
import tempfile
import unittest
from unittest import mock

from app_core.analysis_workflow import (
    AnalysisReportBuilders,
    AnalysisRepositories,
    AnalysisRuntimeContext,
    UploadAnalysisApplicationService,
)


class _FakeCapture:
    def __init__(self, total_frames: int, fps: float):
        self._total_frames = total_frames
        self._fps = fps
        self._frame_index = 0
        self._opened = True

    def isOpened(self) -> bool:
        return self._opened

    def get(self, prop):
        if prop == _FakeCV2.CAP_PROP_FRAME_COUNT:
            return self._total_frames
        if prop == _FakeCV2.CAP_PROP_FPS:
            return self._fps
        return 0

    def read(self):
        if self._frame_index >= self._total_frames:
            return False, None
        self._frame_index += 1
        return True, b"frame"

    def release(self) -> None:
        self._opened = False


class _FakeCV2:
    CAP_PROP_FRAME_COUNT = 7
    CAP_PROP_FPS = 5

    def __init__(self, capture: _FakeCapture):
        self._capture = capture

    def VideoCapture(self, _file_path: str) -> _FakeCapture:  # noqa: N802
        return self._capture


class _FakeResult:
    def plot(self):
        return b"plotted"


class _FakeModel:
    def predict(self, _frame, conf, iou, imgsz, verbose=False):
        return [_FakeResult()]


class ProgressThrottlingTests(unittest.TestCase):
    def test_progress_updates_are_throttled(self):
        temp_dir = tempfile.mkdtemp(prefix="classroom_progress_")
        self.addCleanup(shutil.rmtree, temp_dir, True)

        file_path = os.path.join(temp_dir, "video.mp4")
        with open(file_path, "wb") as handle:
            handle.write(b"x")

        repositories = AnalysisRepositories(
            query_jobs_for_user=lambda *args, **kwargs: None,
            get_latest_job_for_user=lambda *args, **kwargs: None,
            get_visible_job=lambda *args, **kwargs: None,
            get_job_by_id=lambda *args, **kwargs: None,
            create_upload_job_record=lambda *args, **kwargs: None,
            delete_job_artifacts=lambda *args, **kwargs: None,
            get_or_create_report=lambda *args, **kwargs: None,
            get_report_for_job_and_user=lambda *args, **kwargs: None,
            get_latest_reportable_job_for_user=lambda *args, **kwargs: None,
            count_jobs_for_user_by_status=lambda *args, **kwargs: 0,
            count_completed_reports_for_user=lambda *args, **kwargs: 0,
        )
        report_builders = AnalysisReportBuilders(
            build_behavior_report_rows=lambda *args, **kwargs: [],
            build_report_insights=lambda *args, **kwargs: [],
            build_risk_assessment=lambda *args, **kwargs: {"risk_level": "", "risk_summary": ""},
            build_teacher_suggestions=lambda *args, **kwargs: [],
            build_report_gallery=lambda *args, **kwargs: [],
            build_rule_snapshot_for_report=lambda *args, **kwargs: {},
            build_analysis_metrics=lambda *args, **kwargs: {},
            serialize_job=lambda *args, **kwargs: {},
            job_status_message=lambda *args, **kwargs: "",
        )

        fake_capture = _FakeCapture(total_frames=1000, fps=25.0)
        fake_cv2 = _FakeCV2(fake_capture)
        fake_model = _FakeModel()

        class _FakeStorage:
            def list_events(self, *args, **kwargs):
                return []

            def build_history_summary(self, *args, **kwargs):
                return {}

        def get_runtime_setting(key: str):
            if key == "video_analysis_frame_stride":
                return 1
            if key == "yolo_imgsz":
                return 416
            return None

        runtime = AnalysisRuntimeContext(
            behavior_display_names={"sleep": "睡觉"},
            session_factory=object(),
            session_scope=lambda *args, **kwargs: None,
            load_behavior_rules=lambda *args, **kwargs: {},
            event_storage=_FakeStorage(),
            get_model=lambda: fake_model,
            normalize_detections=lambda *args, **kwargs: [],
            map_detections_to_behaviors=lambda *args, **kwargs: {},
            save_alert_snapshot=lambda *args, **kwargs: None,
            calculate_focus_score=lambda *args, **kwargs: {},
            user_can_access_camera=lambda *args, **kwargs: False,
            json_dumps=lambda *args, **kwargs: "{}",
            json_loads=lambda *args, **kwargs: {},
            format_timestamp=lambda *args, **kwargs: "",
            format_datetime=lambda *args, **kwargs: "",
            allowed_video_extensions={".mp4"},
            logger=logging.getLogger("test_progress"),
            cv2=fake_cv2,
            stats_lock=object(),
            current_stats={},
            source_lock=object(),
            source_state={},
            get_behavior_rule_config_payload=lambda *args, **kwargs: {},
            get_runtime_setting=get_runtime_setting,
        )

        service = UploadAnalysisApplicationService(
            runtime=runtime,
            repositories=repositories,
            report_builders=report_builders,
            temporal_analyzer_factory=lambda *_args, **_kwargs: object(),
        )

        service.is_job_deleted = lambda _job_id: False
        service.purge_job_artifacts = lambda *_args, **_kwargs: None
        service.save_report_record = lambda *_args, **_kwargs: None
        service.analyze_uploaded_results = lambda *_args, **_kwargs: {}

        calls = []

        def update_job_record(_job_id: str, **fields) -> None:
            calls.append(fields)

        service.update_job_record = update_job_record

        perf_value = 0.0

        def fake_perf_counter():
            nonlocal perf_value
            current = perf_value
            perf_value += 0.01
            return current

        with mock.patch("app_core.analysis_workflow.time.perf_counter", side_effect=fake_perf_counter), mock.patch(
            "app_core.analysis_workflow.time.time", return_value=1000.0
        ):
            service.process_uploaded_video("job-throttle", 1, file_path)

        progress_updates = [
            fields
            for fields in calls
            if fields.get("status") == "processing" and "progress" in fields and "processed_frames" in fields
        ]

        self.assertGreater(len(progress_updates), 50)
        self.assertLess(len(progress_updates), 200)


if __name__ == "__main__":
    unittest.main()
