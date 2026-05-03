import importlib
import os
import shutil
import sys
import tempfile
import unittest

from database import AlertEvent, create_db_engine, create_session_factory, init_database, session_scope
from storage import EventStorage


class DeletedJobTerminalStateTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="classroom_terminal_delete_")
        self.db_path = os.path.join(self.temp_dir, "terminal.db")
        self.upload_dir = os.path.join(self.temp_dir, "uploads")
        self.old_env = {
            "DATABASE_URL": os.environ.get("DATABASE_URL"),
            "UPLOAD_DIR": os.environ.get("UPLOAD_DIR"),
            "DEFAULT_ADMIN_USERNAME": os.environ.get("DEFAULT_ADMIN_USERNAME"),
            "DEFAULT_ADMIN_EMAIL": os.environ.get("DEFAULT_ADMIN_EMAIL"),
            "DEFAULT_ADMIN_PASSWORD": os.environ.get("DEFAULT_ADMIN_PASSWORD"),
        }
        os.environ["DATABASE_URL"] = "sqlite:///{}".format(self.db_path)
        os.environ["UPLOAD_DIR"] = self.upload_dir
        os.environ.pop("DEFAULT_ADMIN_USERNAME", None)
        os.environ.pop("DEFAULT_ADMIN_EMAIL", None)
        os.environ.pop("DEFAULT_ADMIN_PASSWORD", None)

        if "webapp" in sys.modules:
            self.webapp = importlib.reload(sys.modules["webapp"])
        else:
            import webapp  # type: ignore

            self.webapp = webapp

        self.app = self.webapp.app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        self.webapp.engine.dispose()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

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

    def test_deleted_job_rejects_late_report_and_completion_updates(self):
        register_response = self.register(
            self.client,
            "terminal_user",
            "terminal_user@example.com",
        )
        self.assertEqual(register_response.status_code, 200)

        with self.webapp.session_scope(self.webapp.SessionFactory) as db:
            user = db.query(self.webapp.User).filter_by(username="terminal_user").one()
            user_id = user.id

        service = self.webapp.DEPENDENCIES["analysis_application_service"]
        source_path = os.path.join(self.upload_dir, "late-delete.mp4")
        os.makedirs(self.upload_dir, exist_ok=True)
        with open(source_path, "wb") as handle:
            handle.write(b"demo-video")

        job_id = service.create_upload_job(
            user_id=user_id,
            original_filename="late-delete.mp4",
            stored_filename="late-delete.mp4",
            source_path=source_path,
            source_size_bytes=10,
        )
        with self.webapp.session_scope(self.webapp.SessionFactory) as db:
            job = db.query(self.webapp.VideoAnalysisJob).filter_by(job_id=job_id).one()
            job.status = "deleted"
            job.deleted_at = self.webapp.datetime.utcnow()

        report_saved = service.save_report_record(
            job_id,
            user_id,
            {
                "focus_score": {"score": 90, "level": "高"},
                "summary": {"total_alert_count": 0},
                "behavior_rows": [],
                "insights": [],
                "risk_level": "低",
                "risk_summary": "stable",
                "teacher_suggestions": [],
                "gallery_items": [],
                "rule_snapshot": {},
                "analysis_metrics": {},
            },
        )
        job_updated = service.update_job_record(
            job_id,
            status="completed",
            report_ready=True,
            progress=100.0,
        )

        self.assertFalse(report_saved)
        self.assertFalse(job_updated)
        with self.webapp.session_scope(self.webapp.SessionFactory) as db:
            job = db.query(self.webapp.VideoAnalysisJob).filter_by(job_id=job_id).one()
            report = db.query(self.webapp.AnalysisReport).filter_by(job_id=job_id).one_or_none()
            self.assertEqual(job.status, "deleted")
            self.assertFalse(job.report_ready)
            self.assertIsNotNone(job.deleted_at)
            self.assertIsNone(report)


class ScopedEventRetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="classroom_event_retention_")
        self.snapshot_dir = os.path.join(self.temp_dir, "snapshots")
        db_path = os.path.join(self.temp_dir, "events.db")
        self.engine = create_db_engine("sqlite:///{}".format(db_path))
        self.session_factory = create_session_factory(self.engine)
        init_database(self.engine, self.session_factory)
        self.storage = EventStorage(
            session_factory=self.session_factory,
            snapshot_dir=self.snapshot_dir,
            max_events=2,
        )

    def tearDown(self):
        self.engine.dispose()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_snapshot(self, name: str) -> str:
        os.makedirs(self.snapshot_dir, exist_ok=True)
        path = os.path.join(self.snapshot_dir, name)
        with open(path, "wb") as handle:
            handle.write(b"snapshot")
        return "/snapshots/{}".format(name)

    def test_public_retention_does_not_delete_other_job_scope_events(self):
        user_snapshot_one = self._create_snapshot("job_a_1.jpg")
        user_snapshot_two = self._create_snapshot("job_a_2.jpg")
        self.storage.record_event(
            behavior_key="sleep",
            behavior_name="Sleep",
            duration_seconds=3.0,
            timestamp=1000.0,
            count=1,
            snapshot_path=user_snapshot_one,
            user_id=7,
            job_id="job-a",
        )
        self.storage.record_event(
            behavior_key="sleep",
            behavior_name="Sleep",
            duration_seconds=4.0,
            timestamp=1001.0,
            count=1,
            snapshot_path=user_snapshot_two,
            user_id=7,
            job_id="job-a",
        )

        public_snapshot_one = self._create_snapshot("public_1.jpg")
        public_snapshot_two = self._create_snapshot("public_2.jpg")
        public_snapshot_three = self._create_snapshot("public_3.jpg")
        self.storage.record_event(
            behavior_key="low_head",
            behavior_name="Low Head",
            duration_seconds=2.0,
            timestamp=2000.0,
            count=1,
            snapshot_path=public_snapshot_one,
            user_id=None,
            job_id=None,
        )
        self.storage.record_event(
            behavior_key="low_head",
            behavior_name="Low Head",
            duration_seconds=2.0,
            timestamp=2001.0,
            count=1,
            snapshot_path=public_snapshot_two,
            user_id=None,
            job_id=None,
        )
        self.storage.record_event(
            behavior_key="low_head",
            behavior_name="Low Head",
            duration_seconds=2.0,
            timestamp=2002.0,
            count=1,
            snapshot_path=public_snapshot_three,
            user_id=None,
            job_id=None,
        )

        user_events = self.storage.list_events(user_id=7, job_id="job-a", limit=10)
        public_events = self.storage.list_events(only_public=True, limit=10)

        self.assertEqual(len(user_events), 2)
        self.assertEqual(len(public_events), 2)
        self.assertTrue(os.path.exists(os.path.join(self.snapshot_dir, "job_a_1.jpg")))
        self.assertTrue(os.path.exists(os.path.join(self.snapshot_dir, "job_a_2.jpg")))
        self.assertFalse(os.path.exists(os.path.join(self.snapshot_dir, "public_1.jpg")))
        self.assertTrue(os.path.exists(os.path.join(self.snapshot_dir, "public_2.jpg")))
        self.assertTrue(os.path.exists(os.path.join(self.snapshot_dir, "public_3.jpg")))

        with session_scope(self.session_factory) as session:
            total_events = session.query(AlertEvent).count()
        self.assertEqual(total_events, 4)


if __name__ == "__main__":
    unittest.main()
