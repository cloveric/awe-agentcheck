from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError

from awe_agentcheck.db import Database, SqlTaskRepository
from awe_agentcheck.repository import TaskCreateRecord


def _create_task(repo: SqlTaskRepository, workspace: Path) -> dict:
    return repo.create_task_record(
        TaskCreateRecord(
            title='extra task',
            description='db extra test',
            author_participant='codex#author-A',
            reviewer_participants=['claude#review-B'],
            evolution_level=0,
            evolve_until=None,
            conversation_language='en',
            provider_models={},
            provider_model_params={},
            participant_models={},
            participant_model_params={},
            claude_team_agents=False,
            codex_multi_agents=False,
            claude_team_agents_overrides={},
            codex_multi_agents_overrides={},
            repair_mode='balanced',
            plain_mode=True,
            stream_mode=True,
            debate_mode=True,
            auto_merge=False,
            merge_target_path=None,
            sandbox_mode=False,
            sandbox_workspace_path=None,
            sandbox_generated=False,
            sandbox_cleanup_on_pass=False,
            project_path=str(workspace),
            self_loop_mode=1,
            workspace_path=str(workspace),
            workspace_fingerprint={},
            max_rounds=2,
            test_command='py -m pytest -q',
            lint_command='py -m ruff check .',
        )
    )


def test_sql_repository_basic_status_and_cancel_paths(tmp_path: Path):
    db_file = tmp_path / 'awe-extra.sqlite3'
    db = Database(f"sqlite+pysqlite:///{db_file.as_posix()}")
    db.create_schema()
    repo = SqlTaskRepository(db)
    created = _create_task(repo, tmp_path)
    task_id = created['task_id']

    row = repo.update_task_status(task_id, status='running', reason='started', rounds_completed=1)
    assert row['status'] == 'running'
    assert row['last_gate_reason'] == 'started'
    assert int(row['rounds_completed']) == 1

    row2 = repo.set_cancel_requested(task_id, requested=True)
    assert row2['cancel_requested'] is True
    assert repo.is_cancel_requested(task_id) is True

    row3 = repo.set_cancel_requested(task_id, requested=False)
    assert row3['cancel_requested'] is False
    assert repo.is_cancel_requested(task_id) is False


def test_sql_repository_missing_task_raises_key_error(tmp_path: Path):
    db_file = tmp_path / 'awe-extra-missing.sqlite3'
    db = Database(f"sqlite+pysqlite:///{db_file.as_posix()}")
    db.create_schema()
    repo = SqlTaskRepository(db)

    with pytest.raises(KeyError):
        repo.update_task_status('task-missing', status='running', reason='x')
    with pytest.raises(KeyError):
        repo.set_cancel_requested('task-missing', requested=True)
    with pytest.raises(KeyError):
        repo.is_cancel_requested('task-missing')
    with pytest.raises(KeyError):
        repo.append_event('task-missing', event_type='discussion', payload={'x': 1}, round_number=1)
    with pytest.raises(KeyError):
        repo.list_events('task-missing')


def test_sql_repository_delete_tasks_deduplicates_and_ignores_empty_ids(tmp_path: Path):
    db_file = tmp_path / 'awe-extra-delete.sqlite3'
    db = Database(f"sqlite+pysqlite:///{db_file.as_posix()}")
    db.create_schema()
    repo = SqlTaskRepository(db)
    created = _create_task(repo, tmp_path)
    task_id = created['task_id']
    repo.append_event(task_id, event_type='discussion', payload={'ok': True}, round_number=1)

    assert repo.delete_tasks([]) == 0
    deleted = repo.delete_tasks(['', task_id, task_id, '   '])
    assert deleted == 1
    assert repo.get_task(task_id) is None


def test_sql_repository_retry_helpers_and_lock_error_predicate(tmp_path: Path):
    db_file = tmp_path / 'awe-extra-retry.sqlite3'
    db = Database(f"sqlite+pysqlite:///{db_file.as_posix()}")
    db.create_schema()
    repo = SqlTaskRepository(db)
    assert repo._sqlite_lock_retry_attempts() >= 1
    assert repo._sqlite_lock_backoff_seconds(1) > 0
    assert repo._sqlite_lock_backoff_seconds(50) <= 0.2
    assert repo._is_sqlite_lock_error(Exception('database is locked')) is True
    assert repo._is_sqlite_lock_error(Exception('database table is locked')) is True
    assert repo._is_sqlite_lock_error(Exception('other error')) is False


class _FallbackCounter:
    def __init__(self, next_seq: int):
        self.next_seq = next_seq


class _FallbackSession:
    def __init__(self, *, has_counter: bool):
        self._has_counter = has_counter
        self._counter = _FallbackCounter(7) if has_counter else None
        self.added = []
        self.flushed = False

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name='other'))

    def get(self, model, key, with_for_update=False):  # noqa: ANN001
        if str(getattr(model, '__name__', '')).endswith('TaskEventCounterEntity'):
            return self._counter
        return None

    def execute(self, stmt):  # noqa: ANN001
        # Fallback branch only needs scalar_one from max(seq) query.
        return SimpleNamespace(scalar_one=lambda: 5)

    def add(self, obj):  # noqa: ANN001
        self.added.append(obj)

    def flush(self):
        self.flushed = True


def test_reserve_next_event_seq_fallback_branch_without_counter():
    session = _FallbackSession(has_counter=False)
    assigned = SqlTaskRepository._reserve_next_event_seq(session, 'task-1')
    assert assigned == 6
    assert session.flushed is True
    assert session.added


def test_reserve_next_event_seq_fallback_branch_with_existing_counter():
    session = _FallbackSession(has_counter=True)
    assigned = SqlTaskRepository._reserve_next_event_seq(session, 'task-1')
    assert assigned == 7
    assert session._counter is not None
    assert session._counter.next_seq == 8
    assert session.flushed is True


def test_update_task_status_retries_operational_error_on_lock(tmp_path: Path, monkeypatch):
    db_file = tmp_path / 'awe-extra-update-lock.sqlite3'
    db = Database(f"sqlite+pysqlite:///{db_file.as_posix()}")
    db.create_schema()
    repo = SqlTaskRepository(db)
    created = _create_task(repo, tmp_path)
    task_id = created['task_id']

    original_session = repo.db.session
    state = {'n': 0}

    class _RaiseOnceCtx:
        def __enter__(self):
            state['n'] += 1
            if state['n'] == 1:
                raise OperationalError('update', {}, Exception('database is locked'))
            self._ctx = original_session()
            return self._ctx.__enter__()

        def __exit__(self, exc_type, exc, tb):
            return self._ctx.__exit__(exc_type, exc, tb)

    monkeypatch.setattr(repo.db, 'session', lambda: _RaiseOnceCtx())
    row = repo.update_task_status(task_id, status='running', reason='ok', rounds_completed=1)
    assert row['status'] == 'running'
    assert state['n'] >= 2
