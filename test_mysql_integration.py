import os
import unittest

from sqlalchemy import inspect, text

from database import (
    LATEST_SCHEMA_VERSION,
    create_db_engine,
    create_session_factory,
    init_database,
)


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")


@unittest.skipUnless(
    TEST_DATABASE_URL and TEST_DATABASE_URL.startswith("mysql"),
    "Set TEST_DATABASE_URL=mysql+pymysql://... to enable MySQL integration tests",
)
class MySQLIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_db_engine(TEST_DATABASE_URL)
        self.session_factory = create_session_factory(self.engine)
        init_database(self.engine, self.session_factory)

    def tearDown(self):
        self.engine.dispose()

    def test_schema_migrations_and_indexes_exist(self):
        inspector = inspect(self.engine)
        self.assertIn("schema_migrations", inspector.get_table_names())

        with self.engine.begin() as connection:
            version = connection.execute(text("SELECT MAX(version) FROM schema_migrations")).scalar()
        self.assertEqual(int(version or 0), LATEST_SCHEMA_VERSION)

        alert_indexes = {item.get("name") for item in inspector.get_indexes("alert_events")}
        self.assertIn("idx_alert_events_user_job_ts", alert_indexes)

        job_indexes = {item.get("name") for item in inspector.get_indexes("video_analysis_jobs")}
        self.assertIn("idx_video_jobs_user_status_created", job_indexes)


if __name__ == "__main__":
    unittest.main()

