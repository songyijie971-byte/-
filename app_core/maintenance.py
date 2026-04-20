import argparse
import logging
import os
from typing import List

from app_config import load_runtime_config
from app_core.fs_utils import delete_files, list_files_with_prefix, safe_delete_file
from database import VideoAnalysisJob, create_db_engine, create_session_factory, init_database, session_scope

LOGGER = logging.getLogger(__name__)


def cleanup_orphans() -> int:
    runtime = load_runtime_config()
    engine = create_db_engine(runtime.database_url)
    session_factory = create_session_factory(engine)
    init_database(engine, session_factory)

    upload_dir = os.path.abspath(runtime.upload_dir)
    snapshot_dir = os.path.abspath(os.path.join("data", "alerts"))

    deleted_files = 0
    deleted_jobs = 0
    with session_scope(session_factory) as session:
        jobs: List[VideoAnalysisJob] = (
            session.query(VideoAnalysisJob).filter(VideoAnalysisJob.status == "deleted").all()
        )

    for job in jobs:
        deleted_jobs += 1
        deleted_files += int(
            safe_delete_file(job.source_path or "", allowed_base_dir=upload_dir, logger=LOGGER)
        )
        deleted_files += delete_files(
            list_files_with_prefix(upload_dir, "{}_".format(job.job_id)),
            allowed_base_dir=upload_dir,
            logger=LOGGER,
        )
        deleted_files += delete_files(
            list_files_with_prefix(snapshot_dir, "{}_".format(job.job_id[:8])),
            allowed_base_dir=snapshot_dir,
            logger=LOGGER,
        )

    engine.dispose()
    LOGGER.info("cleanup-orphans done deleted_jobs=%s deleted_files=%s", deleted_jobs, deleted_files)
    return deleted_files


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    parser = argparse.ArgumentParser(prog="app_core.maintenance")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("cleanup-orphans", help="Remove leftover upload/snapshot files for deleted jobs")

    args = parser.parse_args()
    if args.command == "cleanup-orphans":
        cleanup_orphans()
        return

    raise SystemExit(2)


if __name__ == "__main__":
    main()

