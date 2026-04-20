import os
import logging
import time
from typing import Callable, Optional

from app_config import load_runtime_config
from app_core.file_queue import claim_next_message, finalize_message, load_message
from app_core.job_executor import UploadAnalysisTask
from app_core.upload_analysis_worker import run_upload_analysis_task

LOGGER = logging.getLogger(__name__)


def process_next_message(
    queue_dir: str,
    handler: Callable[[UploadAnalysisTask], None] = run_upload_analysis_task,
    logger: Optional[logging.Logger] = None,
) -> bool:
    logger = logger or LOGGER
    claimed = claim_next_message(queue_dir)
    if not claimed:
        return False

    name, processing_path = claimed
    ok = False
    try:
        payload = load_message(processing_path)
        if int(payload.get("schema_version") or 0) != 1:
            raise ValueError("Unsupported schema_version: {}".format(payload.get("schema_version")))
        if payload.get("type") != "upload_analysis":
            raise ValueError("Unsupported message type: {}".format(payload.get("type")))
        task_payload = payload.get("task")
        if not isinstance(task_payload, dict):
            raise ValueError("Missing task payload")

        task = UploadAnalysisTask.from_dict(task_payload)
        if not task.job_id or not task.user_id or not task.file_path:
            raise ValueError("Invalid task payload: {}".format(task_payload))

        handler(task)
        ok = True
        return True
    except Exception:
        logger.exception("Failed to process queue message %s", name)
        return True
    finally:
        try:
            final_path = finalize_message(queue_dir, name, processing_path, ok=ok)
            logger.info("Finalized queue message %s ok=%s path=%s", name, ok, final_path)
        except Exception:
            logger.exception("Failed to finalize queue message %s", name)


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    runtime_config = load_runtime_config()
    queue_dir = runtime_config.job_queue_dir
    poll_seconds = float(runtime_config.job_queue_poll_seconds or 1.0)
    LOGGER.info("Starting queue worker dir=%s poll_seconds=%s", queue_dir, poll_seconds)

    try:
        while True:
            processed = process_next_message(queue_dir)
            if not processed:
                time.sleep(poll_seconds)
    except KeyboardInterrupt:
        LOGGER.info("Queue worker stopped by user")


if __name__ == "__main__":
    main()
