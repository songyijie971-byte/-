import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class FileQueuePaths:
    base_dir: str
    pending_dir: str
    processing_dir: str
    done_dir: str
    failed_dir: str


def _paths(base_dir: str) -> FileQueuePaths:
    base_dir = os.path.abspath(base_dir)
    return FileQueuePaths(
        base_dir=base_dir,
        pending_dir=os.path.join(base_dir, "pending"),
        processing_dir=os.path.join(base_dir, "processing"),
        done_dir=os.path.join(base_dir, "done"),
        failed_dir=os.path.join(base_dir, "failed"),
    )


def ensure_queue_dirs(base_dir: str) -> FileQueuePaths:
    paths = _paths(base_dir)
    os.makedirs(paths.pending_dir, exist_ok=True)
    os.makedirs(paths.processing_dir, exist_ok=True)
    os.makedirs(paths.done_dir, exist_ok=True)
    os.makedirs(paths.failed_dir, exist_ok=True)
    return paths


def enqueue_json(base_dir: str, payload: Dict[str, Any]) -> Tuple[str, str]:
    paths = ensure_queue_dirs(base_dir)
    message_id = uuid.uuid4().hex
    filename = "{}_{}.json".format(int(time.time() * 1000), message_id)
    final_path = os.path.join(paths.pending_dir, filename)
    tmp_path = "{}.tmp".format(final_path)
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)
    os.replace(tmp_path, final_path)
    return message_id, final_path


def _list_pending(paths: FileQueuePaths):
    try:
        entries = os.listdir(paths.pending_dir)
    except FileNotFoundError:
        return []
    files = []
    for name in entries:
        if not name.endswith(".json"):
            continue
        files.append(name)
    files.sort()
    return files


def claim_next_message(base_dir: str) -> Optional[Tuple[str, str]]:
    paths = ensure_queue_dirs(base_dir)
    for name in _list_pending(paths):
        src = os.path.join(paths.pending_dir, name)
        dst = os.path.join(paths.processing_dir, name)
        try:
            os.replace(src, dst)
        except OSError:
            continue
        return name, dst
    return None


def load_message(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def finalize_message(base_dir: str, name: str, processing_path: str, ok: bool) -> str:
    paths = ensure_queue_dirs(base_dir)
    target_dir = paths.done_dir if ok else paths.failed_dir
    final_path = os.path.join(target_dir, name)
    os.replace(processing_path, final_path)
    return final_path

