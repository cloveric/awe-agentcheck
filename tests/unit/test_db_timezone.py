from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from awe_agentcheck.db import Database, SqlTaskRepository
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError


def _create_task(repo: SqlTaskRepository, workspace: Path) -> dict:
    return repo.create_task(
        title='tz task',
        description='tz test',
        author_participant='codex#author-A',
        reviewer_participants=['claude#review-B'],
        evolution_level=0,
        evolve_until=None,
        conversation_language='en',
        provider_models={},
        provider_model_params={},
        claude_team_agents=False,
        codex_multi_agents=False,
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
        max_rounds=1,
        test_command='py -m pytest -q',
        lint_command='py -m ruff check .',
    )


def test_sql_repository_event_timestamps_include_timezone_offset(tmp_path: Path):
    db_file = tmp_path / 'awe-timezone.sqlite3'
    db = Database(f"sqlite+pysqlite:///{db_file.as_posix()}")
    db.create_schema()
    repo = SqlTaskRepository(db)

    created = _create_task(repo, tmp_path)

    repo.append_event(
        created['task_id'],
        event_type='discussion',
        payload={'type': 'discussion', 'output': 'hello'},
        round_number=1,
    )
    rows = repo.list_events(created['task_id'])
    assert rows
    ts = str(rows[0].get('created_at') or '')
    assert ('+' in ts) or ts.endswith('Z')


def test_sqlite_database_sets_busy_timeout_and_foreign_keys(tmp_path: Path):
    db_file = tmp_path / 'awe-pragmas.sqlite3'
    db = Database(f"sqlite+pysqlite:///{db_file.as_posix()}")
    db.create_schema()
    with db.session() as session:
        busy_timeout = int(session.execute(text('PRAGMA busy_timeout')).scalar_one())
        foreign_keys = int(session.execute(text('PRAGMA foreign_keys')).scalar_one())
    assert busy_timeout >= 30000
    assert foreign_keys == 1


def test_sql_repository_append_event_assigns_unique_seq_under_50_threads(tmp_path: Path):
    db_file = tmp_path / 'awe-concurrency.sqlite3'
    db = Database(f"sqlite+pysqlite:///{db_file.as_posix()}")
    db.create_schema()
    repo = SqlTaskRepository(db)
    created = _create_task(repo, tmp_path)

    workers = 50

    def worker(index: int) -> dict:
        return repo.append_event(
            created['task_id'],
            event_type='discussion',
            payload={'worker': index},
            round_number=1,
        )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(worker, range(workers)))

    assert len(results) == workers

    rows = repo.list_events(created['task_id'])
    assert len(rows) == workers
    seqs = [int(row['seq']) for row in rows]
    assert len(set(seqs)) == workers
    assert seqs == list(range(1, workers + 1))


def test_sql_repository_append_event_retries_on_sqlite_lock(tmp_path: Path, monkeypatch):
    db_file = tmp_path / 'awe-lock-retry.sqlite3'
    db = Database(f"sqlite+pysqlite:///{db_file.as_posix()}")
    db.create_schema()
    repo = SqlTaskRepository(db)
    created = _create_task(repo, tmp_path)

    original_reserve = repo._reserve_next_event_seq
    calls = {'n': 0}

    def flaky_reserve(session, task_id: str):
        calls['n'] += 1
        if calls['n'] == 1:
            raise OperationalError('insert', {}, Exception('database is locked'))
        return original_reserve(session, task_id)

    monkeypatch.setattr(repo, '_reserve_next_event_seq', flaky_reserve)
    event = repo.append_event(
        created['task_id'],
        event_type='discussion',
        payload={'type': 'discussion', 'output': 'lock retry'},
        round_number=1,
    )
    assert int(event['seq']) == 1
    assert calls['n'] >= 2


def test_sql_repository_update_task_status_if_returns_none_on_conflict(tmp_path: Path):
    db_file = tmp_path / 'awe-status-conflict.sqlite3'
    db = Database(f"sqlite+pysqlite:///{db_file.as_posix()}")
    db.create_schema()
    repo = SqlTaskRepository(db)
    created = _create_task(repo, tmp_path)
    task_id = created['task_id']

    running = repo.update_task_status(task_id, status='running', reason=None, rounds_completed=0)
    assert running['status'] == 'running'

    updated = repo.update_task_status_if(
        task_id,
        expected_status='queued',
        status='failed_system',
        reason='raced',
        rounds_completed=1,
    )
    assert updated is None

    current = repo.get_task(task_id)
    assert current is not None
    assert current['status'] == 'running'
    assert current['last_gate_reason'] is None


def test_sql_repository_update_task_status_if_raises_for_missing_task(tmp_path: Path):
    db_file = tmp_path / 'awe-status-missing.sqlite3'
    db = Database(f"sqlite+pysqlite:///{db_file.as_posix()}")
    db.create_schema()
    repo = SqlTaskRepository(db)
    with pytest.raises(KeyError):
        repo.update_task_status_if(
            'task-missing',
            expected_status='queued',
            status='running',
            reason=None,
        )


def test_sql_repository_delete_tasks_removes_event_counter_rows(tmp_path: Path):
    db_file = tmp_path / 'awe-delete-counter.sqlite3'
    db = Database(f"sqlite+pysqlite:///{db_file.as_posix()}")
    db.create_schema()
    repo = SqlTaskRepository(db)
    created = _create_task(repo, tmp_path)
    task_id = created['task_id']

    repo.append_event(
        task_id,
        event_type='discussion',
        payload={'type': 'discussion', 'output': 'hello'},
        round_number=1,
    )

    deleted = repo.delete_tasks([task_id])
    assert deleted == 1
    assert repo.get_task(task_id) is None
