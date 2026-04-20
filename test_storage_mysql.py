import json
import os
import shutil
import tempfile
import unittest

from database import (
    SystemConfig,
    create_db_engine,
    create_session_factory,
    init_database,
    load_behavior_rules,
    session_scope,
)
from storage import EventStorage


class MySQLStorageUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="classroom_demo_")
        self.database_path = os.path.join(self.temp_dir, "test.db")
        self.snapshot_dir = os.path.join(self.temp_dir, "alerts")
        self.engine = create_db_engine(f"sqlite:///{self.database_path}")
        self.session_factory = create_session_factory(self.engine)
        init_database(self.engine, self.session_factory)
        self.storage = EventStorage(
            session_factory=self.session_factory,
            snapshot_dir=self.snapshot_dir,
            max_events=100,
        )

    def tearDown(self):
        self.engine.dispose()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_seed_default_behavior_rules(self):
        rules = load_behavior_rules(self.session_factory)

        self.assertIn("low_head", rules)
        self.assertEqual(rules["sleep"]["min_consecutive_frames"], 6)
        self.assertFalse(rules["hand_raise"]["alert_enabled"])

    def test_record_event_and_history_summary_keep_api_shape(self):
        first_ts = 1713175200.0
        second_ts = first_ts + 12
        self.storage.record_event(
            behavior_key="sleep",
            behavior_name="Sleep",
            duration_seconds=4.2,
            timestamp=first_ts,
            count=2,
            snapshot_path="/snapshots/sleep_1.jpg",
        )
        self.storage.record_event(
            behavior_key="low_head",
            behavior_name="Low Head",
            duration_seconds=2.7,
            timestamp=second_ts,
            count=3,
            snapshot_path="/snapshots/low_head_1.jpg",
        )
        self.storage.record_event(
            behavior_key="sleep",
            behavior_name="Sleep",
            duration_seconds=4.8,
            timestamp=second_ts + 5,
            count=1,
            snapshot_path="/snapshots/sleep_2.jpg",
        )

        events = self.storage.list_events(limit=10)
        latest_snapshot = self.storage.get_latest_snapshot()
        summary = self.storage.build_history_summary()

        self.assertEqual(len(events), 3)
        self.assertEqual(events[0]["behavior_key"], "sleep")
        self.assertEqual(events[1]["snapshot_path"], "/snapshots/low_head_1.jpg")
        self.assertEqual(latest_snapshot["behavior_key"], "sleep")
        self.assertEqual(summary["recent_alert_count"], 3)
        self.assertEqual(summary["total_alert_count"], 3)
        self.assertEqual(summary["latest_event"]["behavior_key"], "sleep")
        self.assertEqual(summary["behavior_totals"][0]["behavior_key"], "sleep")
        self.assertIn("recent_timeline", summary)
        self.assertIn("trend_chart", summary)
        self.assertEqual(summary["trend_chart"][-1]["behavior_key"], "sleep")

    def test_invalid_config_value_falls_back_to_default_rule(self):
        with session_scope(self.session_factory) as session:
            config = (
                session.query(SystemConfig)
                .filter(SystemConfig.config_key == "behavior_rule.sleep")
                .one()
            )
            config.config_value = "{broken json"

        rules = load_behavior_rules(self.session_factory)

        self.assertEqual(rules["sleep"]["min_consecutive_frames"], 6)
        self.assertEqual(rules["sleep"]["alert_after_seconds"], 4.0)

    def test_updated_config_is_loaded_from_database(self):
        with session_scope(self.session_factory) as session:
            config = (
                session.query(SystemConfig)
                .filter(SystemConfig.config_key == "behavior_rule.turn_talk")
                .one()
            )
            config.config_value = json.dumps(
                {
                    "min_consecutive_frames": 9,
                    "alert_after_seconds": 7.5,
                    "alert_enabled": False,
                }
            )

        rules = load_behavior_rules(self.session_factory)

        self.assertEqual(rules["turn_talk"]["min_consecutive_frames"], 9)
        self.assertEqual(rules["turn_talk"]["alert_after_seconds"], 7.5)
        self.assertFalse(rules["turn_talk"]["alert_enabled"])


if __name__ == "__main__":
    unittest.main()
