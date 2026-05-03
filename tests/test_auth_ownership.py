import importlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock


class AuthAndOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="classroom_auth_")
        self.db_path = os.path.join(self.temp_dir, "auth.db")
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

    def get_csrf_token(self, client):
        response = client.get("/api/me")
        payload = response.get_json() or {}
        return payload.get("csrf_token") or ""

    def csrf_headers(self, client):
        token = self.get_csrf_token(client)
        return {"X-CSRF-Token": token} if token else {}

    def tearDown(self):
        self.webapp.engine.dispose()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

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

    def login(self, client, account, password):
        return client.post(
            "/api/auth/login",
            headers=self.csrf_headers(client),
            json={"account": account, "password": password},
        )

    def change_password(self, client, password):
        return client.post(
            "/api/auth/change_password",
            headers=self.csrf_headers(client),
            json={"password": password, "confirm_password": password},
        )

    def create_job_bundle(self, user_id, job_id="job-alpha"):
        with self.webapp.session_scope(self.webapp.SessionFactory) as db:
            db.add(
                self.webapp.VideoAnalysisJob(
                    job_id=job_id,
                    user_id=user_id,
                    original_filename="sample.mp4",
                    stored_filename="{}_sample.mp4".format(job_id),
                    source_path=os.path.join(self.upload_dir, "{}_sample.mp4".format(job_id)),
                    status="completed",
                    progress=100.0,
                    processed_frames=120,
                    total_frames=120,
                    duration_seconds=12.0,
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
                        {"score": 88, "level": "高", "summary_text": "稳定"}
                    ),
                    summary_json=self.webapp._json_dumps(
                        {
                            "recent_alert_count": 1,
                            "total_alert_count": 1,
                            "behavior_totals": [
                                {
                                    "behavior_key": "sleep",
                                    "behavior_name": "Sleep",
                                    "count": 1,
                                }
                            ],
                            "trend_items": [],
                            "trend_chart": [],
                            "recent_timeline": [],
                            "latest_event": None,
                        }
                    ),
                    behavior_rows_json=self.webapp._json_dumps(
                        [
                            {
                                "behavior_key": "sleep",
                                "behavior_name": "Sleep",
                                "count": 1,
                                "avg_duration": 5.0,
                                "max_duration": 5.0,
                                "avg_people": 1.0,
                                "max_people": 1,
                            }
                        ]
                    ),
                    insights_json=self.webapp._json_dumps(["测试洞察"]),
                    risk_level="中",
                    risk_summary="测试风险说明",
                    teacher_suggestions_json=self.webapp._json_dumps(["测试建议"]),
                    gallery_items_json=self.webapp._json_dumps([]),
                )
            )
            db.add(
                self.webapp.AlertEvent(
                    event_id="evt-{}".format(job_id),
                    behavior_key="sleep",
                    behavior_name="Sleep",
                    duration_seconds=5.0,
                    event_timestamp=1713175200.0,
                    count=1,
                    snapshot_path="/snapshots/{}_sleep.jpg".format(job_id),
                    user_id=user_id,
                    job_id=job_id,
                )
            )

    def test_register_login_logout_and_password_hash(self):
        response = self.register(self.client, "alice", "alice@example.com")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["user"]["role"], "user")

        with self.webapp.session_scope(self.webapp.SessionFactory) as db:
            user = db.query(self.webapp.User).filter_by(username="alice").one()
            self.assertNotEqual(user.password_hash, "secret123")
            self.assertTrue(user.password_hash)

        self.assertTrue(self.client.get("/api/me").get_json()["authenticated"])
        self.assertTrue(
            self.client.post(
                "/api/auth/logout",
                headers=self.csrf_headers(self.client),
            ).get_json()["ok"]
        )
        self.assertFalse(self.client.get("/api/me").get_json()["authenticated"])

        login_response = self.login(self.client, "alice", "secret123")
        self.assertEqual(login_response.status_code, 200)
        self.assertTrue(login_response.get_json()["ok"])

    def test_default_admin_login_works_without_env_configuration(self):
        response = self.login(self.client, "admin", "admin123456")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["user"]["role"], "admin")
        self.assertTrue(payload["user"]["force_password_change"])
        self.assertEqual(payload["redirect_url"], "/change-password")

    def test_first_registered_user_becomes_admin_when_database_has_no_admin(self):
        with self.webapp.session_scope(self.webapp.SessionFactory) as db:
            db.query(self.webapp.User).filter_by(role="admin").delete()

        response = self.register(self.client, "bootstrap_admin", "bootstrap@example.com")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["user"]["role"], "admin")
        self.assertFalse(payload["user"]["force_password_change"])

    def test_default_admin_must_change_password_before_accessing_system(self):
        login_response = self.login(self.client, "admin", "admin123456")

        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(self.client.get("/").status_code, 302)
        self.assertIn("/change-password", self.client.get("/").location)

        api_blocked = self.client.get("/api/history")
        self.assertEqual(api_blocked.status_code, 403)
        blocked_payload = api_blocked.get_json()
        self.assertTrue(blocked_payload["force_password_change"])
        self.assertEqual(blocked_payload["redirect_url"], "/change-password")

        change_response = self.change_password(self.client, "new-admin-456")
        self.assertEqual(change_response.status_code, 200)
        changed_payload = change_response.get_json()
        self.assertFalse(changed_payload["user"]["force_password_change"])

        self.assertEqual(self.client.get("/").status_code, 200)

        self.client.post("/api/auth/logout")
        self.assertEqual(self.login(self.client, "admin", "admin123456").status_code, 400)
        self.assertEqual(self.login(self.client, "admin", "new-admin-456").status_code, 200)

    def test_login_required_and_user_cannot_access_camera(self):
        redirect_response = self.client.get("/my/uploads")
        self.assertEqual(redirect_response.status_code, 302)
        self.assertIn("/login", redirect_response.location)

        user_client = self.app.test_client()
        self.register(user_client, "bob", "bob@example.com")

        index_response = user_client.get("/")
        self.assertEqual(index_response.status_code, 302)
        self.assertIn("/my/uploads", index_response.location)

        self.assertEqual(user_client.get("/video_feed").status_code, 403)
        self.assertEqual(user_client.get("/api/stats").status_code, 403)

    def test_admin_can_update_behavior_rules_and_user_cannot(self):
        admin_client = self.app.test_client()
        self.assertEqual(self.login(admin_client, "admin", "admin123456").status_code, 200)
        self.assertEqual(self.change_password(admin_client, "rules-admin-456").status_code, 200)

        rules_response = admin_client.get("/api/admin/behavior_rules")
        self.assertEqual(rules_response.status_code, 200)
        payload = rules_response.get_json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["items"])

        low_head_rule = next(item for item in payload["items"] if item["behavior_key"] == "low_head")
        low_head_rule["min_consecutive_frames"] = 8
        low_head_rule["alert_after_seconds"] = 5.5
        low_head_rule["alert_enabled"] = True

        save_response = admin_client.post(
            "/api/admin/behavior_rules",
            headers=self.csrf_headers(admin_client),
            json={"items": payload["items"]},
        )
        self.assertEqual(save_response.status_code, 200)
        saved_payload = save_response.get_json()
        saved_low_head = next(
            item for item in saved_payload["items"] if item["behavior_key"] == "low_head"
        )
        self.assertEqual(saved_low_head["min_consecutive_frames"], 8)
        self.assertEqual(saved_low_head["alert_after_seconds"], 5.5)

        user_client = self.app.test_client()
        self.register(user_client, "rule_user", "rule_user@example.com")
        self.assertEqual(user_client.get("/api/admin/behavior_rules").status_code, 403)

    def test_upload_job_is_bound_to_owner_and_hidden_from_other_user(self):
        client_a = self.app.test_client()
        self.register(client_a, "owner_a", "a@example.com")

        with mock.patch.object(self.webapp.threading.Thread, "start", return_value=None):
            response = client_a.post(
                "/api/upload_video",
                headers=self.csrf_headers(client_a),
                data={"video": (io.BytesIO(b"fake-video"), "lesson.mp4")},
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        job_id = response.get_json()["job_id"]

        with self.webapp.session_scope(self.webapp.SessionFactory) as db:
            job = db.query(self.webapp.VideoAnalysisJob).filter_by(job_id=job_id).one()
            owner = db.query(self.webapp.User).filter_by(username="owner_a").one()
            self.assertEqual(job.user_id, owner.id)

        client_b = self.app.test_client()
        self.register(client_b, "owner_b", "b@example.com")

        jobs_payload = client_b.get("/api/my/uploads").get_json()
        self.assertEqual(jobs_payload["items"], [])
        self.assertEqual(client_b.get("/api/my/uploads/{}".format(job_id)).status_code, 404)

    def test_report_access_delete_and_event_cleanup_are_owner_scoped(self):
        client_a = self.app.test_client()
        self.register(client_a, "report_a", "report_a@example.com")
        client_b = self.app.test_client()
        self.register(client_b, "report_b", "report_b@example.com")

        with self.webapp.session_scope(self.webapp.SessionFactory) as db:
            user_a = db.query(self.webapp.User).filter_by(username="report_a").one()
            self.create_job_bundle(user_a.id, job_id="job-alpha")

        self.assertEqual(client_a.get("/report/job-alpha").status_code, 200)
        self.assertEqual(client_b.get("/report/job-alpha").status_code, 404)

        delete_response = client_a.delete(
            "/api/my/uploads/job-alpha",
            headers=self.csrf_headers(client_a),
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertTrue(delete_response.get_json()["ok"])

        self.assertEqual(client_a.get("/report/job-alpha").status_code, 404)
        self.assertEqual(client_a.get("/api/my/uploads").get_json()["items"], [])

        with self.webapp.session_scope(self.webapp.SessionFactory) as db:
            job = db.query(self.webapp.VideoAnalysisJob).filter_by(job_id="job-alpha").one()
            self.assertEqual(job.status, "deleted")
            self.assertIsNone(
                db.query(self.webapp.AnalysisReport).filter_by(job_id="job-alpha").one_or_none()
            )
            self.assertEqual(
                db.query(self.webapp.AlertEvent).filter_by(job_id="job-alpha").count(),
                0,
            )

    def test_history_scope_user_vs_admin_public(self):
        user_client = self.app.test_client()
        self.register(user_client, "history_user", "history@example.com")

        with self.webapp.session_scope(self.webapp.SessionFactory) as db:
            user = db.query(self.webapp.User).filter_by(username="history_user").one()
            db.add(
                self.webapp.AlertEvent(
                    event_id="evt-public",
                    behavior_key="sleep",
                    behavior_name="Sleep",
                    duration_seconds=4.0,
                    event_timestamp=1713175200.0,
                    count=1,
                    snapshot_path="/snapshots/public_sleep.jpg",
                    user_id=None,
                    job_id=None,
                )
            )
            db.add(
                self.webapp.AlertEvent(
                    event_id="evt-private",
                    behavior_key="low_head",
                    behavior_name="Low Head",
                    duration_seconds=3.0,
                    event_timestamp=1713175201.0,
                    count=1,
                    snapshot_path="/snapshots/private_low_head.jpg",
                    user_id=user.id,
                    job_id="job-private",
                )
            )

        user_history = user_client.get("/api/history").get_json()
        self.assertEqual(user_history["summary"]["total_alert_count"], 1)
        self.assertEqual(len(user_history["events"]), 1)
        self.assertEqual(user_history["events"][0]["event_id"], "evt-private")

        admin_client = self.app.test_client()
        login_response = self.login(admin_client, "admin", "admin123456")
        self.assertEqual(login_response.status_code, 200)
        change_response = self.change_password(admin_client, "history-admin-456")
        self.assertEqual(change_response.status_code, 200)

        admin_history = admin_client.get("/api/history").get_json()
        self.assertEqual(admin_history["summary"]["total_alert_count"], 1)
        self.assertEqual(admin_history["events"][0]["event_id"], "evt-public")


if __name__ == "__main__":
    unittest.main()
