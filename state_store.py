"""프로세스 간 JSON 상태 파일을 안전하게 읽고 쓰는 공통 유틸리티."""

from contextlib import contextmanager
import json
import os
import tempfile
import threading
import time
from typing import Any, Callable, Optional

try:
    import fcntl
except ImportError:  # Windows 오프라인 시험 환경
    fcntl = None


_thread_locks = {}
_thread_locks_guard = threading.Lock()


def _thread_lock_for(path: str) -> threading.RLock:
    absolute = os.path.abspath(path)
    with _thread_locks_guard:
        return _thread_locks.setdefault(absolute, threading.RLock())


@contextmanager
def _state_lock(path: str):
    """동일 프로세스 스레드와 Jetson의 여러 프로세스를 함께 직렬화한다."""
    thread_lock = _thread_lock_for(path)
    with thread_lock:
        lock_path = path + ".lock"
        directory = os.path.dirname(lock_path) or "."
        os.makedirs(directory, exist_ok=True)
        with open(lock_path, "a+", encoding="utf-8") as lock_file:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def read_json(path: str, default: Optional[Any] = None) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, TypeError):
        return default


def _atomic_write_json_unlocked(path: str, value: Any) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".drone-state-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        for attempt in range(20):
            try:
                os.replace(temp_path, path)
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.005)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def atomic_write_json(path: str, value: Any) -> None:
    """임시 파일을 완전히 쓴 뒤 잠금 구간에서 원자적으로 교체한다."""
    with _state_lock(path):
        _atomic_write_json_unlocked(path, value)


def update_json(
    path: str,
    updater: Callable[[Any], Optional[Any]],
    default: Optional[Any] = None,
) -> Optional[Any]:
    """잠금 상태에서 최신 값을 읽고 조건부 갱신한다.

    updater가 None을 반환하면 파일을 바꾸지 않는다. 기록했다면 새 값을 반환한다.
    """
    with _state_lock(path):
        current = read_json(path, default)
        updated = updater(current)
        if updated is None:
            return None
        _atomic_write_json_unlocked(path, updated)
        return updated
