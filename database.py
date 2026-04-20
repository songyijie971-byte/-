import json
import logging
import os
from contextlib import contextmanager
from typing import Dict, Iterator, Optional
from urllib.parse import quote

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, create_engine, inspect, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.sql import func
from werkzeug.security import generate_password_hash

from behavior_core import BEHAVIOR_DISPLAY_NAMES, BEHAVIOR_RULES

LOGGER = logging.getLogger(__name__)

Base = declarative_base()


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(64), unique=True, nullable=False, index=True)
    behavior_key = Column(String(32), nullable=False, index=True)
    behavior_name = Column(String(64), nullable=False)
    duration_seconds = Column(Float, nullable=False)
    event_timestamp = Column(Float, nullable=False, index=True)
    count = Column(Integer, nullable=False)
    snapshot_path = Column(String(255), nullable=True)
    user_id = Column(Integer, nullable=True, index=True)
    job_id = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SystemConfig(Base):
    __tablename__ = "system_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_key = Column(String(128), unique=True, nullable=False, index=True)
    config_type = Column(String(32), nullable=False, index=True)
    config_value = Column(Text, nullable=False)
    description = Column(String(255), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(16), nullable=False, default="user", index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    force_password_change = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class VideoAnalysisJob(Base):
    __tablename__ = "video_analysis_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    original_filename = Column(String(255), nullable=False)
    stored_filename = Column(String(255), nullable=False)
    source_path = Column(String(255), nullable=False)
    status = Column(String(24), nullable=False, default="queued", index=True)
    progress = Column(Float, nullable=False, default=0.0)
    processed_frames = Column(Integer, nullable=False, default=0)
    total_frames = Column(Integer, nullable=False, default=0)
    duration_seconds = Column(Float, nullable=False, default=0.0)
    fps = Column(Float, nullable=False, default=0.0)
    frame_stride = Column(Integer, nullable=False, default=1)
    report_ready = Column(Boolean, nullable=False, default=False)
    source_size_bytes = Column(Integer, nullable=False, default=0)
    status_detail = Column(Text, nullable=True)
    failure_stage = Column(String(64), nullable=True)
    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    queued_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AnalysisReport(Base):
    __tablename__ = "analysis_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    generated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    focus_score_json = Column(Text, nullable=False, default="{}")
    summary_json = Column(Text, nullable=False, default="{}")
    behavior_rows_json = Column(Text, nullable=False, default="[]")
    insights_json = Column(Text, nullable=False, default="[]")
    risk_level = Column(String(16), nullable=False, default="")
    risk_summary = Column(Text, nullable=False, default="")
    teacher_suggestions_json = Column(Text, nullable=False, default="[]")
    gallery_items_json = Column(Text, nullable=False, default="[]")
    rule_snapshot_json = Column(Text, nullable=False, default="{}")
    analysis_metrics_json = Column(Text, nullable=False, default="{}")


def build_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    host = os.getenv("MYSQL_HOST", "127.0.0.1")
    port = os.getenv("MYSQL_PORT", "3306")
    user = os.getenv("MYSQL_USER", "root")
    password = os.getenv("MYSQL_PASSWORD", "")
    database = os.getenv("MYSQL_DATABASE", "classroom_demo")
    charset = os.getenv("MYSQL_CHARSET", "utf8mb4")

    user = quote(user, safe="")
    password = quote(password, safe="")
    database = quote(database, safe="")
    return (
        f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
        f"?charset={charset}"
    )


def create_db_engine(database_url: Optional[str] = None):
    url = database_url or build_database_url()
    engine_kwargs = {"pool_pre_ping": True, "future": True}
    if url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **engine_kwargs)


def create_session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@contextmanager
def session_scope(session_factory) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


LATEST_SCHEMA_VERSION = 1


def _ensure_schema_migrations_table(connection) -> None:
    connection.execute(
        text("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER NOT NULL)")
    )


def _get_schema_version(connection) -> int:
    try:
        value = connection.execute(text("SELECT MAX(version) FROM schema_migrations")).scalar()
    except Exception:
        return 0
    return int(value or 0)


def _set_schema_version(connection, version: int) -> None:
    connection.execute(text("DELETE FROM schema_migrations"))
    connection.execute(
        text("INSERT INTO schema_migrations (version) VALUES (:version)"),
        {"version": int(version)},
    )


def _ensure_index(connection, table_name: str, index_name: str, columns) -> None:
    inspector = inspect(connection)
    try:
        existing = {item.get("name") for item in inspector.get_indexes(table_name)}
    except Exception:
        existing = set()
    if index_name in existing:
        return

    column_sql = ", ".join(columns)
    if connection.dialect.name == "sqlite":
        statement = "CREATE INDEX IF NOT EXISTS {} ON {} ({})".format(
            index_name,
            table_name,
            column_sql,
        )
    else:
        statement = "CREATE INDEX {} ON {} ({})".format(index_name, table_name, column_sql)
    connection.execute(text(statement))


def _ensure_alert_event_columns(connection) -> None:
    inspector = inspect(connection)
    if "alert_events" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("alert_events")}
    statements = []
    if "user_id" not in existing_columns:
        statements.append("ALTER TABLE alert_events ADD COLUMN user_id INTEGER NULL")
    if "job_id" not in existing_columns:
        statements.append("ALTER TABLE alert_events ADD COLUMN job_id VARCHAR(64) NULL")

    if not statements:
        return

    for statement in statements:
        connection.execute(text(statement))


def _ensure_user_columns(connection) -> None:
    inspector = inspect(connection)
    if "users" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("users")}
    statements = []
    if "force_password_change" not in existing_columns:
        statements.append(
            "ALTER TABLE users ADD COLUMN force_password_change BOOLEAN NOT NULL DEFAULT 0"
        )

    if not statements:
        return

    for statement in statements:
        connection.execute(text(statement))


def _ensure_analysis_report_columns(connection) -> None:
    inspector = inspect(connection)
    if "analysis_reports" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("analysis_reports")}
    add_statements = []
    backfill_statements = []
    if "rule_snapshot_json" not in existing_columns:
        add_statements.append(
            "ALTER TABLE analysis_reports ADD COLUMN rule_snapshot_json TEXT NULL"
        )
        backfill_statements.extend(
            [
                "UPDATE analysis_reports SET rule_snapshot_json = '{}' WHERE rule_snapshot_json IS NULL",
            ]
        )
    if "analysis_metrics_json" not in existing_columns:
        add_statements.append(
            "ALTER TABLE analysis_reports ADD COLUMN analysis_metrics_json TEXT NULL"
        )
        backfill_statements.extend(
            [
                "UPDATE analysis_reports SET analysis_metrics_json = '{}' WHERE analysis_metrics_json IS NULL",
            ]
        )

    if not add_statements and not backfill_statements:
        return

    for statement in add_statements:
        connection.execute(text(statement))
    for statement in backfill_statements:
        connection.execute(text(statement))


def _ensure_video_analysis_job_columns(connection) -> None:
    inspector = inspect(connection)
    if "video_analysis_jobs" not in inspector.get_table_names():
        return

    existing_columns = {
        column["name"] for column in inspector.get_columns("video_analysis_jobs")
    }
    add_statements = []
    backfill_statements = []
    if "source_size_bytes" not in existing_columns:
        add_statements.append(
            "ALTER TABLE video_analysis_jobs ADD COLUMN source_size_bytes INTEGER NOT NULL DEFAULT 0"
        )
    if "status_detail" not in existing_columns:
        add_statements.append(
            "ALTER TABLE video_analysis_jobs ADD COLUMN status_detail TEXT NULL"
        )
    if "failure_stage" not in existing_columns:
        add_statements.append(
            "ALTER TABLE video_analysis_jobs ADD COLUMN failure_stage VARCHAR(64) NULL"
        )
    if "error_code" not in existing_columns:
        add_statements.append(
            "ALTER TABLE video_analysis_jobs ADD COLUMN error_code VARCHAR(64) NULL"
        )
    if "error_message" not in existing_columns:
        add_statements.append(
            "ALTER TABLE video_analysis_jobs ADD COLUMN error_message TEXT NULL"
        )
    if "queued_at" not in existing_columns:
        add_statements.append(
            "ALTER TABLE video_analysis_jobs ADD COLUMN queued_at DATETIME NULL"
        )
        backfill_statements.append(
            "UPDATE video_analysis_jobs SET queued_at = created_at WHERE queued_at IS NULL"
        )
    if "started_at" not in existing_columns:
        add_statements.append(
            "ALTER TABLE video_analysis_jobs ADD COLUMN started_at DATETIME NULL"
        )
    if "finished_at" not in existing_columns:
        add_statements.append(
            "ALTER TABLE video_analysis_jobs ADD COLUMN finished_at DATETIME NULL"
        )
    if "deleted_at" not in existing_columns:
        add_statements.append(
            "ALTER TABLE video_analysis_jobs ADD COLUMN deleted_at DATETIME NULL"
        )

    if not add_statements and not backfill_statements:
        return

    for statement in add_statements:
        connection.execute(text(statement))
    for statement in backfill_statements:
        connection.execute(text(statement))


def _migrate_to_v1(connection) -> None:
    _ensure_alert_event_columns(connection)
    _ensure_user_columns(connection)
    _ensure_analysis_report_columns(connection)
    _ensure_video_analysis_job_columns(connection)
    _ensure_index(
        connection,
        table_name="alert_events",
        index_name="idx_alert_events_user_job_ts",
        columns=("user_id", "job_id", "event_timestamp"),
    )
    _ensure_index(
        connection,
        table_name="video_analysis_jobs",
        index_name="idx_video_jobs_user_status_created",
        columns=("user_id", "status", "created_at"),
    )


def run_schema_migrations(engine) -> int:
    with engine.begin() as connection:
        _ensure_schema_migrations_table(connection)
        current_version = _get_schema_version(connection)
        if current_version >= LATEST_SCHEMA_VERSION:
            if current_version > LATEST_SCHEMA_VERSION:
                LOGGER.warning(
                    "Database schema version %s is newer than supported version %s",
                    current_version,
                    LATEST_SCHEMA_VERSION,
                )
            return int(current_version)

        for target in range(int(current_version) + 1, LATEST_SCHEMA_VERSION + 1):
            if target == 1:
                _migrate_to_v1(connection)
            else:
                raise RuntimeError("Unknown migration target version: {}".format(target))
            _set_schema_version(connection, target)
            current_version = target

        return int(current_version)


def seed_default_system_configs(session: Session) -> None:
    existing_keys = {
        row[0]
        for row in session.query(SystemConfig.config_key)
        .filter(SystemConfig.config_type == "behavior_rule")
        .all()
    }
    for behavior_key, rule in BEHAVIOR_RULES.items():
        config_key = f"behavior_rule.{behavior_key}"
        if config_key in existing_keys:
            continue
        session.add(
            SystemConfig(
                config_key=config_key,
                config_type="behavior_rule",
                config_value=json.dumps(rule, ensure_ascii=False),
                description=f"{BEHAVIOR_DISPLAY_NAMES[behavior_key]} behavior rule",
            )
        )


def seed_default_admin(session: Session) -> None:
    def _read_bool_env(name: str, default: bool = False) -> bool:
        raw = os.getenv(name)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    def _production_env() -> bool:
        value = (os.getenv("APP_ENV") or os.getenv("FLASK_ENV") or "").strip().lower()
        return value in {"prod", "production"}

    if _read_bool_env("DISABLE_DEFAULT_ADMIN_SEED", False):
        return

    seed_enabled = _read_bool_env("SEED_DEFAULT_ADMIN", default=not _production_env())
    if not seed_enabled:
        LOGGER.warning("Skipped seeding default admin (SEED_DEFAULT_ADMIN disabled)")
        return

    admin_exists = session.query(User.id).filter(User.role == "admin").first()
    if admin_exists:
        return

    username = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")
    email = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@classroom.local")
    password = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123456")

    def _is_weak_password(value: str) -> bool:
        if not value:
            return True
        trimmed = value.strip()
        if len(trimmed) < 10:
            return True
        lowered = trimmed.lower()
        if lowered in {"admin", "admin123456", "password", "123456", "12345678", "qwerty"}:
            return True
        if lowered == (username or "").strip().lower():
            return True
        return False

    force_password_change = _is_weak_password(password)

    duplicate = (
        session.query(User.id)
        .filter((User.username == username) | (User.email == email))
        .first()
    )
    if duplicate:
        return

    session.add(
        User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            role="admin",
            is_active=True,
            force_password_change=force_password_change,
        )
    )
    if force_password_change:
        LOGGER.warning(
            "Seeded default admin account username=%s force_password_change=true",
            username,
        )
    else:
        LOGGER.warning("Seeded default admin account username=%s", username)


def init_database(engine, session_factory) -> None:
    Base.metadata.create_all(engine)
    run_schema_migrations(engine)
    with session_scope(session_factory) as session:
        seed_default_system_configs(session)
        seed_default_admin(session)


def load_behavior_rules(session_factory) -> Dict[str, Dict[str, object]]:
    loaded_rules: Dict[str, Dict[str, object]] = {}
    try:
        with session_scope(session_factory) as session:
            configs = (
                session.query(SystemConfig)
                .filter(SystemConfig.config_type == "behavior_rule")
                .all()
            )
            for config in configs:
                behavior_key = config.config_key.split(".", 1)[-1]
                if behavior_key not in BEHAVIOR_RULES:
                    continue
                try:
                    value = json.loads(config.config_value)
                except json.JSONDecodeError:
                    LOGGER.exception("Invalid JSON in system config %s", config.config_key)
                    continue

                default_rule = BEHAVIOR_RULES[behavior_key]
                loaded_rules[behavior_key] = {
                    "min_consecutive_frames": int(
                        value.get(
                            "min_consecutive_frames",
                            default_rule["min_consecutive_frames"],
                        )
                    ),
                    "alert_after_seconds": value.get(
                        "alert_after_seconds",
                        default_rule["alert_after_seconds"],
                    ),
                    "alert_enabled": bool(
                        value.get("alert_enabled", default_rule["alert_enabled"])
                    ),
                }
    except Exception:
        LOGGER.exception("Failed to load behavior rules from database")
        return dict(BEHAVIOR_RULES)

    merged_rules = dict(BEHAVIOR_RULES)
    merged_rules.update(loaded_rules)
    return merged_rules
