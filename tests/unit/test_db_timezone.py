from __future__ import annotations

from pathlib import Path

from awe_agentcheck.db import Database, SqlTaskRepository


def test_sql_repository_event_timestamps_include_timezone_offset(tmp_path: Path):
    db_file = tmp_path / 'awe-timezone.sqlite3'
    db = Database(f"sqlite+pysqlite:///{db_file.as_posix()}")
    db.create_schema()
    repo = SqlTaskRepository(db)

    created = repo.create_task(
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
        project_path=str(tmp_path),
        self_loop_mode=1,
        workspace_path=str(tmp_path),
        max_rounds=1,
        test_command='py -m pytest -q',
        lint_command='py -m ruff check .',
    )

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
