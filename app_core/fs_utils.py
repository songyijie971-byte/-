import os
from typing import Iterable, List, Optional


def _abspath(path: str) -> str:
    return os.path.abspath(os.path.realpath(path))


def is_within_dir(path: str, base_dir: str) -> bool:
    try:
        path_abs = _abspath(path)
        base_abs = _abspath(base_dir)
        return os.path.commonpath([path_abs, base_abs]) == base_abs
    except Exception:
        return False


def safe_delete_file(path: str, allowed_base_dir: str, logger: Optional[object] = None) -> bool:
    if not path:
        return False
    if not is_within_dir(path, allowed_base_dir):
        if logger:
            logger.warning("Refused to delete path outside allowed dir: %s", path)
        return False
    try:
        os.remove(path)
        return True
    except FileNotFoundError:
        return False
    except PermissionError:
        if logger:
            logger.warning("Failed to delete file due to permission error: %s", path)
        return False
    except OSError:
        if logger:
            logger.exception("Failed to delete file: %s", path)
        return False


def list_files_with_prefix(directory: str, prefix: str) -> List[str]:
    if not directory or not os.path.isdir(directory):
        return []
    files: List[str] = []
    try:
        for name in os.listdir(directory):
            if not name.startswith(prefix):
                continue
            files.append(os.path.join(directory, name))
    except OSError:
        return []
    return files


def delete_files(paths: Iterable[str], allowed_base_dir: str, logger: Optional[object] = None) -> int:
    deleted = 0
    for path in paths:
        if safe_delete_file(path, allowed_base_dir=allowed_base_dir, logger=logger):
            deleted += 1
    return deleted

