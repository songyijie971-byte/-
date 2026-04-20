from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
import time
from typing import Any, Callable, Dict, Optional

from app_core.file_queue import enqueue_json, ensure_queue_dirs


@dataclass(frozen=True)
class UploadAnalysisTask:
    job_id: str
    user_id: int
    file_path: str

    def to_dict(self) -> Dict[str, Any]:
        return {"job_id": self.job_id, "user_id": self.user_id, "file_path": self.file_path}

    @staticmethod
    def from_dict(payload: Dict[str, Any]) -> "UploadAnalysisTask":
        return UploadAnalysisTask(
            job_id=str(payload.get("job_id") or ""),
            user_id=int(payload.get("user_id") or 0),
            file_path=str(payload.get("file_path") or ""),
        )


@dataclass(frozen=True)
class JobSubmission:
    job_name: str
    backend: str
    task: UploadAnalysisTask


class JobExecutor:
    def submit_upload_analysis(self, task: UploadAnalysisTask) -> JobSubmission:
        raise NotImplementedError


class UploadAnalysisDispatcher:
    def dispatch(self, task: UploadAnalysisTask) -> JobSubmission:
        raise NotImplementedError


class ExecutorBackedUploadAnalysisDispatcher(UploadAnalysisDispatcher):
    def __init__(self, executor: JobExecutor) -> None:
        self._executor = executor

    def dispatch(self, task: UploadAnalysisTask) -> JobSubmission:
        return self._executor.submit_upload_analysis(task)


def _run_upload_analysis_entrypoint(handler_module: str, handler_name: str, task: UploadAnalysisTask) -> None:
    module = __import__(handler_module, fromlist=[handler_name])
    handler = getattr(module, handler_name)
    handler(task)


class LocalThreadJobExecutor(JobExecutor):
    def __init__(self, threading_module, logger, task_handler: Callable[[UploadAnalysisTask], None]) -> None:
        self._threading = threading_module
        self._logger = logger
        self._task_handler = task_handler

    def submit_upload_analysis(self, task: UploadAnalysisTask) -> JobSubmission:
        job_name = "upload-analysis-{}".format(task.job_id[:8])
        thread = self._threading.Thread(
            target=self._task_handler,
            args=(task,),
            name=job_name,
            daemon=True,
        )
        thread.start()
        self._logger.info("Submitted background job %s via local thread executor", job_name)
        return JobSubmission(job_name=job_name, backend="local_thread", task=task)


class ProcessPoolJobExecutor(JobExecutor):
    def __init__(
        self,
        logger,
        handler_module: str,
        handler_name: str,
        max_workers: int = 2,
        process_pool_factory: Optional[Callable[..., ProcessPoolExecutor]] = None,
    ) -> None:
        self._logger = logger
        self._handler_module = handler_module
        self._handler_name = handler_name
        self._max_workers = max_workers
        factory = process_pool_factory or ProcessPoolExecutor
        self._executor_factory = factory
        self._executor = None

    def _ensure_executor(self) -> ProcessPoolExecutor:
        if self._executor is None:
            self._executor = self._executor_factory(max_workers=self._max_workers)
        return self._executor

    def submit_upload_analysis(self, task: UploadAnalysisTask) -> JobSubmission:
        job_name = "upload-analysis-{}".format(task.job_id[:8])
        self._ensure_executor().submit(
            _run_upload_analysis_entrypoint,
            self._handler_module,
            self._handler_name,
            task,
        )
        self._logger.info("Submitted background job %s via process pool executor", job_name)
        return JobSubmission(job_name=job_name, backend="process_pool", task=task)

    def shutdown(self, wait: bool = False) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=wait)


class QueueJobExecutor(JobExecutor):
    def __init__(self, logger, queue_dir: str) -> None:
        self._logger = logger
        self._queue_dir = queue_dir

    def submit_upload_analysis(self, task: UploadAnalysisTask) -> JobSubmission:
        ensure_queue_dirs(self._queue_dir)
        payload = {
            "schema_version": 1,
            "type": "upload_analysis",
            "submitted_at": time.time(),
            "task": task.to_dict(),
        }
        message_id, path = enqueue_json(self._queue_dir, payload)
        job_name = "upload-analysis-{}".format(task.job_id[:8])
        self._logger.info("Enqueued background job %s id=%s path=%s", job_name, message_id, path)
        return JobSubmission(job_name=job_name, backend="file_queue", task=task)
