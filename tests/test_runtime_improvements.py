import importlib
import io
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

import numpy as np


class RuntimeImprovementsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="classroom_runtime_")
        self.db_path = os.path.join(self.temp_dir, "runtime.db")
        self.upload_dir = os.path.join(self.temp_dir, "uploads")
        self.model_path = os.path.join(self.temp_dir, "dummy-model.pt")
        with open(self.model_path, "wb") as handle:
            handle.write(b"model")
        self.old_env = {
            "DATABASE_URL": os.environ.get("DATABASE_URL"),
            "UPLOAD_DIR": os.environ.get("UPLOAD_DIR"),
            "MAX_UPLOAD_SIZE_MB": os.environ.get("MAX_UPLOAD_SIZE_MB"),
            "YOLO_MODEL_PATH": os.environ.get("YOLO_MODEL_PATH"),
            "JOB_EXECUTOR_BACKEND": os.environ.get("JOB_EXECUTOR_BACKEND"),
            "JOB_EXECUTOR_PROCESS_WORKERS": os.environ.get("JOB_EXECUTOR_PROCESS_WORKERS"),
            "JOB_QUEUE_DIR": os.environ.get("JOB_QUEUE_DIR"),
            "JOB_QUEUE_POLL_SECONDS": os.environ.get("JOB_QUEUE_POLL_SECONDS"),
            "DEFAULT_ADMIN_USERNAME": os.environ.get("DEFAULT_ADMIN_USERNAME"),
            "DEFAULT_ADMIN_EMAIL": os.environ.get("DEFAULT_ADMIN_EMAIL"),
            "DEFAULT_ADMIN_PASSWORD": os.environ.get("DEFAULT_ADMIN_PASSWORD"),
        }
        os.environ["DATABASE_URL"] = "sqlite:///{}".format(self.db_path)
        os.environ["UPLOAD_DIR"] = self.upload_dir
        os.environ["MAX_UPLOAD_SIZE_MB"] = "1"
        os.environ["YOLO_MODEL_PATH"] = self.model_path
        os.environ.pop("DEFAULT_ADMIN_USERNAME", None)
        os.environ.pop("DEFAULT_ADMIN_EMAIL", None)
        os.environ.pop("DEFAULT_ADMIN_PASSWORD", None)
        self._reload_webapp()

    def tearDown(self):
        self.webapp.engine.dispose()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _reload_webapp(self):
        if "webapp" in sys.modules:
            self.webapp = importlib.reload(sys.modules["webapp"])
        else:
            import webapp  # type: ignore

            self.webapp = webapp
        self.app = self.webapp.app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def get_csrf_token(self, client):
        response = client.get("/api/me")
        payload = response.get_json() or {}
        return payload.get("csrf_token") or ""

    def csrf_headers(self, client):
        token = self.get_csrf_token(client)
        return {"X-CSRF-Token": token} if token else {}

    def register(self, client, username, email, password="secret123"):
        return client.post(
            "/api/auth/register",
            headers=self.csrf_headers(client),
            json={
                "username": username,
                "email": email,
                "password": password,
                "confirm_password": password,
            },
        )

    def create_report_bundle(self, user_id, job_id="job-report"):
        with self.webapp.session_scope(self.webapp.SessionFactory) as db:
            db.add(
                self.webapp.VideoAnalysisJob(
                    job_id=job_id,
                    user_id=user_id,
                    original_filename="report.mp4",
                    stored_filename="report.mp4",
                    source_path=os.path.join(self.upload_dir, "report.mp4"),
                    status="completed",
                    status_detail="分析完成，报告已生成，可直接打开分析报告。",
                    progress=100.0,
                    processed_frames=60,
                    total_frames=60,
                    duration_seconds=6.0,
                    fps=10.0,
                    frame_stride=3,
                    report_ready=True,
                )
            )
            db.add(
                self.webapp.AnalysisReport(
                    job_id=job_id,
                    user_id=user_id,
                    focus_score_json=self.webapp._json_dumps(
                        {
                            "score": 92,
                            "level": "高",
                            "summary_text": "课堂状态稳定",
                            "rule_text": "100 - 低头×12 - 睡觉×20 - 转头交谈×15 + 举手×4",
                            "limits_text": "该评分仅用于课堂状态可视化展示，不直接等同于教学质量评价。",
                        }
                    ),
                    summary_json=self.webapp._json_dumps(
                        {
                            "recent_alert_count": 0,
                            "total_alert_count": 0,
                            "behavior_totals": [],
                            "trend_items": [],
                            "trend_chart": [],
                            "recent_timeline": [],
                            "latest_event": None,
                        }
                    ),
                    behavior_rows_json=self.webapp._json_dumps([]),
                    insights_json=self.webapp._json_dumps(["测试报告洞察"]),
                    risk_level="低",
                    risk_summary="课堂整体秩序较稳定",
                    teacher_suggestions_json=self.webapp._json_dumps(["保持当前授课节奏"]),
                    gallery_items_json=self.webapp._json_dumps([]),
                    rule_snapshot_json=self.webapp._json_dumps(
                        {
                            "version_label": "旧规则版本",
                            "rules": [
                                {
                                    "behavior_key": "sleep",
                                    "behavior_name": "睡觉",
                                    "description": "测试规则快照",
                                    "min_consecutive_frames": 6,
                                    "alert_after_seconds": 4.0,
                                    "alert_enabled": True,
                                }
                            ],
                        }
                    ),
                    analysis_metrics_json=self.webapp._json_dumps(
                        {
                            "analysis_elapsed_seconds": 1.2,
                            "processed_fps": 50.0,
                            "frame_coverage_ratio": 100.0,
                            "realtime_ratio": 0.2,
                            "sampled_frames": 60,
                            "total_frames": 60,
                        }
                    ),
                )
            )

    def make_test_png(self):
        image = np.full((24, 24, 3), 180, dtype=np.uint8)
        ok, encoded = self.webapp.DEPENDENCIES["analysis_application_service"].runtime.cv2.imencode(".png", image)
        self.assertTrue(ok)
        return io.BytesIO(encoded.tobytes())

    def build_fake_image_model(self):
        class _Scalar:
            def __init__(self, value):
                self.value = value

            def item(self):
                return self.value

        class _TensorLike:
            def __init__(self, values):
                self.values = values

            def tolist(self):
                return list(self.values)

        class _Box:
            def __init__(self, cls_id, conf, bbox):
                self.cls = _Scalar(cls_id)
                self.conf = _Scalar(conf)
                self.xyxy = [_TensorLike(bbox)]

        class _Result:
            def __init__(self, frame):
                self.boxes = [
                    _Box(0, 0.91, [4.0, 8.0, 48.0, 72.0]),
                    _Box(4, 0.82, [54.0, 12.0, 96.0, 84.0]),
                ]
                self._frame = frame

            def plot(self):
                return self._frame

        class _FakeModel:
            names = {0: "low_head_candidate", 4: "hand_raise_candidate"}

            def predict(self, frame, conf=0.35, iou=0.45, imgsz=416, verbose=False):
                return [_Result(frame)]

        return _FakeModel()

    def test_health_endpoint_reports_core_components(self):
        response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["database"]["status"], "ok")
        self.assertTrue(payload["storage"]["writable"])
        self.assertIn("camera", payload)
        self.assertIn("model", payload)
        self.assertIn("runtime", payload)
        self.assertEqual(payload["runtime"]["job_executor_backend"], "thread")

    def test_missing_model_is_reported_by_health_endpoint(self):
        self.webapp.engine.dispose()
        os.environ["YOLO_MODEL_PATH"] = os.path.join(self.temp_dir, "missing.onnx")
        self._reload_webapp()

        response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(payload["model"]["status"], "warning")
        self.assertFalse(payload["model"]["exists"])

    def test_process_executor_configuration_is_loaded(self):
        self.webapp.engine.dispose()
        os.environ["JOB_EXECUTOR_BACKEND"] = "process"
        os.environ["JOB_EXECUTOR_PROCESS_WORKERS"] = "3"
        self._reload_webapp()

        response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["runtime"]["job_executor_backend"], "process")
        self.assertEqual(payload["runtime"]["job_executor_process_workers"], 3)

    def test_queue_backend_enqueues_and_worker_processes_messages(self):
        self.webapp.engine.dispose()
        queue_dir = os.path.join(self.temp_dir, "job_queue")
        os.environ["JOB_EXECUTOR_BACKEND"] = "queue"
        os.environ["JOB_QUEUE_DIR"] = queue_dir
        self._reload_webapp()

        user_client = self.app.test_client()
        self.register(user_client, "queue_backend_user", "queue_backend_user@example.com")

        upload_response = user_client.post(
            "/api/upload_video",
            headers=self.csrf_headers(user_client),
            data={"video": (io.BytesIO(b"demo-video"), "lesson.mp4")},
            content_type="multipart/form-data",
        )
        self.assertEqual(upload_response.status_code, 200)
        payload = upload_response.get_json()
        self.assertEqual(payload["job_backend"], "file_queue")
        job_id = payload["job_id"]

        pending_dir = os.path.join(queue_dir, "pending")
        pending_files = [name for name in os.listdir(pending_dir) if name.endswith(".json")]
        self.assertEqual(len(pending_files), 1)

        from app_core.queue_worker import process_next_message

        seen_tasks = []

        def handler(task):
            seen_tasks.append(task)

        processed = process_next_message(queue_dir, handler=handler)
        self.assertTrue(processed)
        self.assertEqual(len(seen_tasks), 1)
        self.assertEqual(seen_tasks[0].job_id, job_id)

        pending_files = [name for name in os.listdir(pending_dir) if name.endswith(".json")]
        done_dir = os.path.join(queue_dir, "done")
        done_files = [name for name in os.listdir(done_dir) if name.endswith(".json")]
        self.assertEqual(len(pending_files), 0)
        self.assertEqual(len(done_files), 1)

        health = self.client.get("/api/health").get_json()
        self.assertEqual(health["job_queue"]["backend"], "queue")
        self.assertEqual(health["job_queue"]["pending"], 0)
        self.assertEqual(health["job_queue"]["done"], 1)

    def test_queue_worker_moves_to_failed_on_exception(self):
        self.webapp.engine.dispose()
        queue_dir = os.path.join(self.temp_dir, "job_queue")
        os.environ["JOB_EXECUTOR_BACKEND"] = "queue"
        os.environ["JOB_QUEUE_DIR"] = queue_dir
        self._reload_webapp()

        user_client = self.app.test_client()
        self.register(user_client, "queue_fail_user", "queue_fail_user@example.com")

        upload_response = user_client.post(
            "/api/upload_video",
            headers=self.csrf_headers(user_client),
            data={"video": (io.BytesIO(b"demo-video"), "lesson.mp4")},
            content_type="multipart/form-data",
        )
        self.assertEqual(upload_response.status_code, 200)

        from app_core.queue_worker import process_next_message

        def handler(_task):
            raise RuntimeError("boom")

        processed = process_next_message(queue_dir, handler=handler)
        self.assertTrue(processed)

        failed_dir = os.path.join(queue_dir, "failed")
        failed_files = [name for name in os.listdir(failed_dir) if name.endswith(".json")]
        self.assertEqual(len(failed_files), 1)

    def test_upload_validation_rejects_empty_and_oversized_files(self):
        user_client = self.app.test_client()
        self.register(user_client, "upload_user", "upload_user@example.com")

        empty_response = user_client.post(
            "/api/upload_video",
            headers=self.csrf_headers(user_client),
            data={"video": (io.BytesIO(b""), "empty.mp4")},
            content_type="multipart/form-data",
        )
        self.assertEqual(empty_response.status_code, 400)
        self.assertIn("为空", empty_response.get_json()["message"])

        oversized_response = user_client.post(
            "/api/upload_video",
            headers=self.csrf_headers(user_client),
            data={"video": (io.BytesIO(b"x" * (self.webapp.MAX_UPLOAD_BYTES + 1)), "big.mp4")},
            content_type="multipart/form-data",
        )
        self.assertEqual(oversized_response.status_code, 413)
        self.assertIn("过大", oversized_response.get_json()["message"])

    def test_analysis_status_exposes_timing_and_status_detail(self):
        user_client = self.app.test_client()
        self.register(user_client, "queue_user", "queue_user@example.com")

        with mock.patch.object(self.webapp.threading.Thread, "start", return_value=None):
            upload_response = user_client.post(
                "/api/upload_video",
                headers=self.csrf_headers(user_client),
                data={"video": (io.BytesIO(b"demo-video"), "lesson.mp4")},
                content_type="multipart/form-data",
            )
        self.assertEqual(upload_response.status_code, 200)
        self.assertEqual(upload_response.get_json()["job_backend"], "local_thread")

        status_response = user_client.get("/api/analysis_status")
        payload = status_response.get_json()

        self.assertEqual(payload["status"], "queued")
        self.assertNotEqual(payload["queued_at"], "--")
        self.assertEqual(payload["started_at"], "--")
        self.assertIn("等待后台分析", payload["status_detail"])

    def test_image_analysis_endpoint_returns_single_frame_payload(self):
        user_client = self.app.test_client()
        self.register(user_client, "image_user", "image_user@example.com")
        service = self.webapp.DEPENDENCIES["analysis_application_service"]
        object.__setattr__(service.runtime, "get_model", lambda: self.build_fake_image_model())

        response = user_client.post(
            "/api/analyze_image",
            headers=self.csrf_headers(user_client),
            data={"image": (self.make_test_png(), "lesson.png")},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["available"])
        self.assertEqual(payload["analysis_type"], "image")
        self.assertEqual(payload["source_mode"], "image")
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(len(payload["behavior_items"]), 2)
        self.assertEqual(payload["detections_count"], 2)
        self.assertIn("/image-uploads/images/user_", payload["annotated_url"])

    def test_image_analysis_rejects_non_image_extensions(self):
        user_client = self.app.test_client()
        self.register(user_client, "image_invalid_user", "image_invalid_user@example.com")

        response = user_client.post(
            "/api/analyze_image",
            headers=self.csrf_headers(user_client),
            data={"image": (io.BytesIO(b"not-an-image"), "lesson.mp4")},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertIn("jpg", payload["message"])

    def test_latest_image_analysis_endpoint_reuses_last_result(self):
        user_client = self.app.test_client()
        self.register(user_client, "image_latest_user", "image_latest_user@example.com")
        service = self.webapp.DEPENDENCIES["analysis_application_service"]
        object.__setattr__(service.runtime, "get_model", lambda: self.build_fake_image_model())

        upload_response = user_client.post(
            "/api/analyze_image",
            headers=self.csrf_headers(user_client),
            data={"image": (self.make_test_png(), "latest.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(upload_response.status_code, 200)
        upload_payload = upload_response.get_json()

        latest_response = user_client.get("/api/image_analysis/latest")
        self.assertEqual(latest_response.status_code, 200)
        latest_payload = latest_response.get_json()
        self.assertTrue(latest_payload["available"])
        self.assertEqual(latest_payload["filename"], "latest.png")
        self.assertEqual(latest_payload["annotated_url"], upload_payload["annotated_url"])
        image_response = user_client.get(latest_payload["annotated_url"])
        self.assertEqual(image_response.status_code, 200)
        image_response.get_data()
        image_response.close()

    def test_delete_job_is_idempotent_and_marks_deleted_at(self):
        user_client = self.app.test_client()
        self.register(user_client, "delete_user", "delete_user@example.com")

        with mock.patch.object(self.webapp.threading.Thread, "start", return_value=None):
            upload_response = user_client.post(
                "/api/upload_video",
                headers=self.csrf_headers(user_client),
                data={"video": (io.BytesIO(b"demo-video"), "lesson.mp4")},
                content_type="multipart/form-data",
            )
        job_id = upload_response.get_json()["job_id"]

        first_delete = user_client.delete(
            "/api/my/uploads/{}".format(job_id),
            headers=self.csrf_headers(user_client),
        )
        second_delete = user_client.delete(
            "/api/my/uploads/{}".format(job_id),
            headers=self.csrf_headers(user_client),
        )

        self.assertEqual(first_delete.status_code, 200)
        self.assertEqual(second_delete.status_code, 200)
        self.assertIn("已删除", second_delete.get_json()["message"])

        with self.webapp.session_scope(self.webapp.SessionFactory) as db:
            job = db.query(self.webapp.VideoAnalysisJob).filter_by(job_id=job_id).one()
            self.assertEqual(job.status, "deleted")
            self.assertIsNotNone(job.deleted_at)
            self.assertIn("后台线程会自动停止处理", job.status_detail)

    def test_delete_job_removes_upload_and_snapshot_files(self):
        user_client = self.app.test_client()
        self.register(user_client, "delete_files_user", "delete_files_user@example.com")

        with mock.patch.object(self.webapp.threading.Thread, "start", return_value=None):
            upload_response = user_client.post(
                "/api/upload_video",
                headers=self.csrf_headers(user_client),
                data={"video": (io.BytesIO(b"demo-video"), "lesson.mp4")},
                content_type="multipart/form-data",
            )
        self.assertEqual(upload_response.status_code, 200)
        payload = upload_response.get_json()
        job_id = payload["job_id"]
        stored_name = payload["source_url"].split("/")[-1]

        upload_path = os.path.join(self.upload_dir, stored_name)
        self.assertTrue(os.path.exists(upload_path))

        original_snapshot_dir = self.webapp.APP_CONTEXT.event_storage.snapshot_dir
        snapshot_dir = os.path.join(self.temp_dir, "alerts")
        os.makedirs(snapshot_dir, exist_ok=True)
        self.webapp.APP_CONTEXT.event_storage.snapshot_dir = snapshot_dir
        self.addCleanup(
            setattr,
            self.webapp.APP_CONTEXT.event_storage,
            "snapshot_dir",
            original_snapshot_dir,
        )

        snapshot_path = os.path.join(snapshot_dir, "{}_snapshot.jpg".format(job_id[:8]))
        with open(snapshot_path, "wb") as handle:
            handle.write(b"fake-snapshot")
        self.assertTrue(os.path.exists(snapshot_path))

        delete_response = user_client.delete(
            "/api/my/uploads/{}".format(job_id),
            headers=self.csrf_headers(user_client),
        )

        self.assertEqual(delete_response.status_code, 200)
        delete_payload = delete_response.get_json()
        self.assertGreaterEqual(delete_payload.get("deleted_files", 0), 2)
        self.assertFalse(os.path.exists(upload_path))
        self.assertFalse(os.path.exists(snapshot_path))

    def test_report_page_uses_stored_rule_snapshot(self):
        user_client = self.app.test_client()
        self.register(user_client, "report_user", "report_user@example.com")

        with self.webapp.session_scope(self.webapp.SessionFactory) as db:
            user = db.query(self.webapp.User).filter_by(username="report_user").one()
            self.create_report_bundle(user.id, job_id="job-report")
            config = (
                db.query(self.webapp.SystemConfig)
                .filter(self.webapp.SystemConfig.config_key == "behavior_rule.sleep")
                .one()
            )
            config.config_value = self.webapp._json_dumps(
                {
                    "min_consecutive_frames": 9,
                    "alert_after_seconds": 7.0,
                    "alert_enabled": True,
                }
            )

        response = user_client.get("/report/job-report")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("旧规则版本", html)
        self.assertIn("规则快照", html)

    def test_camera_placeholder_frame_is_available_without_live_frame(self):
        with self.webapp.frame_lock:
            self.webapp.runtime_refs["latest_camera_frame"] = None

        frame = self.webapp.get_display_frame()

        self.assertIsNotNone(frame)
        self.assertGreater(frame.shape[0], 0)
        self.assertGreater(frame.shape[1], 0)

    def test_focus_score_is_consistent_between_web_and_worker_services(self):
        import app_core.upload_analysis_worker as upload_analysis_worker

        upload_analysis_worker = importlib.reload(upload_analysis_worker)
        self.addCleanup(setattr, upload_analysis_worker, "_WORKER_SERVICE", None)

        stable_counts = {
            "low_head": 2,
            "sleep": 1,
            "turn_talk": 1,
            "hand_raise": 3,
        }

        worker_service = upload_analysis_worker.get_worker_service()

        self.assertEqual(
            self.webapp.calculate_focus_score(stable_counts),
            worker_service.runtime.calculate_focus_score(stable_counts),
        )

    def test_web_get_model_initializes_only_once_under_concurrency(self):
        self.webapp.APP_CONTEXT.model = None
        call_count = 0
        call_lock = threading.Lock()

        class FakeModel:
            pass

        def fake_yolo(*_args, **_kwargs):
            nonlocal call_count
            time.sleep(0.05)
            with call_lock:
                call_count += 1
            return FakeModel()

        results = []
        errors = []

        def load_model():
            try:
                results.append(self.webapp.get_model())
            except Exception as exc:
                errors.append(exc)

        with mock.patch.object(self.webapp, "YOLO", side_effect=fake_yolo):
            threads = [threading.Thread(target=load_model) for _ in range(6)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(call_count, 1)
        self.assertEqual(len(results), 6)
        self.assertTrue(all(result is results[0] for result in results))

    def test_worker_get_model_initializes_only_once_under_concurrency(self):
        import app_core.upload_analysis_worker as upload_analysis_worker

        upload_analysis_worker = importlib.reload(upload_analysis_worker)
        self.addCleanup(setattr, upload_analysis_worker, "_WORKER_SERVICE", None)

        call_count = 0
        call_lock = threading.Lock()

        class FakeModel:
            pass

        def fake_yolo(*_args, **_kwargs):
            nonlocal call_count
            time.sleep(0.05)
            with call_lock:
                call_count += 1
            return FakeModel()

        results = []
        errors = []

        def load_model(worker_service):
            try:
                results.append(worker_service.runtime.get_model())
            except Exception as exc:
                errors.append(exc)

        with mock.patch.object(upload_analysis_worker, "YOLO", side_effect=fake_yolo):
            worker_service = upload_analysis_worker.get_worker_service()
            threads = [
                threading.Thread(target=load_model, args=(worker_service,))
                for _ in range(6)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(call_count, 1)
        self.assertEqual(len(results), 6)
        self.assertTrue(all(result is results[0] for result in results))


if __name__ == "__main__":
    unittest.main()
