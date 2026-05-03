import importlib
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock


class LoginRateLimitTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="classroom_rate_limit_")
        self.db_path = os.path.join(self.temp_dir, "rate_limit.db")
        self.upload_dir = os.path.join(self.temp_dir, "uploads")
        self.old_env = {
            "DATABASE_URL": os.environ.get("DATABASE_URL"),
            "UPLOAD_DIR": os.environ.get("UPLOAD_DIR"),
            "DEFAULT_ADMIN_USERNAME": os.environ.get("DEFAULT_ADMIN_USERNAME"),
            "DEFAULT_ADMIN_EMAIL": os.environ.get("DEFAULT_ADMIN_EMAIL"),
            "DEFAULT_ADMIN_PASSWORD": os.environ.get("DEFAULT_ADMIN_PASSWORD"),
            "TRUST_X_FORWARDED_FOR": os.environ.get("TRUST_X_FORWARDED_FOR"),
        }
        os.environ["DATABASE_URL"] = "sqlite:///{}".format(self.db_path)
        os.environ["UPLOAD_DIR"] = self.upload_dir
        os.environ.pop("DEFAULT_ADMIN_USERNAME", None)
        os.environ.pop("DEFAULT_ADMIN_EMAIL", None)
        os.environ.pop("DEFAULT_ADMIN_PASSWORD", None)
        os.environ.pop("TRUST_X_FORWARDED_FOR", None)

        if "webapp" in sys.modules:
            self.webapp = importlib.reload(sys.modules["webapp"])
        else:
            import webapp  # type: ignore

            self.webapp = webapp

        self.app = self.webapp.app
        self.app.config["TESTING"] = True

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

    def login_api(self, client, account, password, remote_addr="127.0.0.1", headers=None):
        request_headers = dict(self.csrf_headers(client))
        if headers:
            request_headers.update(headers)
        return client.post(
            "/api/auth/login",
            headers=request_headers,
            json={"account": account, "password": password},
            environ_base={"REMOTE_ADDR": remote_addr},
        )

    def login_page(self, client, account, password, remote_addr="127.0.0.1"):
        csrf_token = self.get_csrf_token(client)
        return client.post(
            "/login",
            data={"account": account, "password": password, "csrf_token": csrf_token},
            environ_base={"REMOTE_ADDR": remote_addr},
            follow_redirects=False,
        )

    def test_api_login_rate_limit_blocks_after_too_many_failures_and_recovers(self):
        register_client = self.app.test_client()
        self.register(register_client, "limit_user", "limit_user@example.com", password="goodpass")

        client = self.app.test_client()
        now = 1000.0
        with mock.patch("auth_service.time.time", side_effect=lambda: now):
            for _ in range(10):
                response = self.login_api(client, "limit_user", "wrong", remote_addr="1.2.3.4")
                self.assertEqual(response.status_code, 400)

            blocked = self.login_api(client, "limit_user", "wrong", remote_addr="1.2.3.4")
            self.assertEqual(blocked.status_code, 429)
            payload = blocked.get_json()
            self.assertFalse(payload["ok"])

            now += 601.0
            recovered = self.login_api(client, "limit_user", "wrong", remote_addr="1.2.3.4")
            self.assertEqual(recovered.status_code, 400)

    def test_login_page_rate_limit_returns_429(self):
        register_client = self.app.test_client()
        self.register(register_client, "page_user", "page_user@example.com", password="goodpass")

        client = self.app.test_client()
        now = 2000.0
        with mock.patch("auth_service.time.time", side_effect=lambda: now):
            for _ in range(10):
                response = self.login_page(client, "page_user", "wrong", remote_addr="5.6.7.8")
                self.assertEqual(response.status_code, 200)

            blocked = self.login_page(client, "page_user", "wrong", remote_addr="5.6.7.8")
            self.assertEqual(blocked.status_code, 429)

    def test_spoofed_forwarded_for_does_not_bypass_limit_by_default(self):
        register_client = self.app.test_client()
        self.register(register_client, "xff_user", "xff_user@example.com", password="goodpass")

        client = self.app.test_client()
        now = 3000.0
        with mock.patch("auth_service.time.time", side_effect=lambda: now):
            for attempt in range(10):
                response = self.login_api(
                    client,
                    "xff_user",
                    "wrong",
                    remote_addr="9.9.9.9",
                    headers={"X-Forwarded-For": "203.0.113.{}".format(attempt)},
                )
                self.assertEqual(response.status_code, 400)

            blocked = self.login_api(
                client,
                "xff_user",
                "wrong",
                remote_addr="9.9.9.9",
                headers={"X-Forwarded-For": "198.51.100.8"},
            )
            self.assertEqual(blocked.status_code, 429)


if __name__ == "__main__":
    unittest.main()
