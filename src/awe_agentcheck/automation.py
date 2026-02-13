from __future__ import annotations

import ctypes
from datetime import datetime
from contextlib import contextmanager
import os
from pathlib import Path
from typing import Callable, Iterator


def parse_until(value: str) -> datetime:
    text = (value or '').strip()
    if not text:
        raise ValueError('until datetime cannot be empty')

    for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    try:
        # Accept ISO style like 2026-02-12T07:00:00
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f'invalid datetime format: {value}') from exc


def should_switch_to_fallback(status: str, reason: str | None) -> bool:
    s = (status or '').strip().lower()
    r = (reason or '').strip().lower()
    if s != 'failed_system':
        return False
    return 'claude' in r or 'command failed' in r


def should_switch_back_to_primary(status: str, reason: str | None) -> bool:
    s = (status or '').strip().lower()
    r = (reason or '').strip().lower()
    if s != 'failed_system':
        return False
    if 'provider=codex' in r and ('command_timeout' in r or 'command_not_found' in r or 'provider_limit' in r):
        return True
    return False


def is_provider_limit_reason(reason: str | None, *, provider: str | None = None) -> bool:
    text = (reason or '').strip().lower()
    if 'provider_limit' not in text:
        return False
    if provider:
        return f'provider={provider.strip().lower()}' in text
    return True


def should_retry_start_for_concurrency_limit(status: str, reason: str | None) -> bool:
    s = (status or '').strip().lower()
    r = (reason or '').strip().lower()
    return s == 'queued' and 'concurrency_limit' in r


def _pid_exists_default(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == 'nt':
        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, pid)
        if handle == 0:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _read_lock_pid(lock_path: Path) -> int | None:
    try:
        content = lock_path.read_text(encoding='utf-8').strip()
    except FileNotFoundError:
        return None
    if not content:
        return None
    first_line = content.splitlines()[0].strip()
    try:
        return int(first_line)
    except ValueError:
        return None


@contextmanager
def acquire_single_instance(
    lock_path: Path,
    *,
    pid: int | None = None,
    pid_exists: Callable[[int], bool] | None = None,
) -> Iterator[None]:
    target = Path(lock_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    current_pid = pid or os.getpid()
    pid_exists_fn = pid_exists or _pid_exists_default

    existing_pid = _read_lock_pid(target)
    if existing_pid is not None and pid_exists_fn(existing_pid):
        raise RuntimeError(f'lock already held by pid={existing_pid}')
    if target.exists():
        target.unlink()

    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        payload = f'{current_pid}\n{datetime.now().isoformat()}\n'
        os.write(fd, payload.encode('utf-8'))
    finally:
        os.close(fd)

    try:
        yield
    finally:
        owner_pid = _read_lock_pid(target)
        if owner_pid is None or owner_pid == current_pid:
            try:
                target.unlink()
            except FileNotFoundError:
                pass
