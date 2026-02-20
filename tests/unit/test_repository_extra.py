from __future__ import annotations

import json

import pytest

from awe_agentcheck.domain.events import EventType
from awe_agentcheck.repository import (
    InMemoryTaskRepository,
    TaskCreateRecord,
    _coerce_meta_bool,
    decode_reviewer_meta,
    decode_task_meta,
    encode_reviewer_meta,
    encode_task_meta,
)


def _record(**overrides) -> TaskCreateRecord:
    base = dict(
        title='repo-test',
        description='desc',
        author_participant='codex#author-A',
        reviewer_participants=['claude#review-B'],
        evolution_level=2,
        evolve_until='2026-02-18T07:00:00',
        conversation_language='zh',
        provider_models={'codex': 'gpt-5.3-codex'},
        provider_model_params={'codex': '-c model_reasoning_effort=xhigh'},
        participant_models={'codex#author-A': 'gpt-5.3-codex'},
        participant_model_params={'codex#author-A': '-c model_reasoning_effort=xhigh'},
        claude_team_agents=True,
        codex_multi_agents=True,
        claude_team_agents_overrides={'claude#review-B': True},
        codex_multi_agents_overrides={'codex#author-A': False},
        repair_mode='structural',
        plain_mode=False,
        stream_mode=True,
        debate_mode=True,
        auto_merge=False,
        merge_target_path='C:/target',
        sandbox_mode=True,
        sandbox_workspace_path='C:/repo-lab',
        sandbox_generated=True,
        sandbox_cleanup_on_pass=True,
        project_path='C:/repo',
        self_loop_mode=1,
        workspace_path='C:/repo-lab',
        workspace_fingerprint={'schema': 'workspace_fingerprint.v1'},
        max_rounds=3,
        test_command='py -m pytest -q',
        lint_command='py -m ruff check .',
    )
    base.update(overrides)
    return TaskCreateRecord(**base)


def test_inmemory_repository_crud_and_event_paths():
    repo = InMemoryTaskRepository()
    row = repo.create_task_record(_record())
    task_id = row['task_id']
    assert row['status'] == 'queued'
    assert row['conversation_language'] == 'zh'

    listed = repo.list_tasks(limit=10)
    assert listed and listed[0]['task_id'] == task_id
    assert repo.get_task(task_id)['task_id'] == task_id
    assert repo.get_task('missing') is None

    updated = repo.update_task_status(task_id, status='running', reason='started', rounds_completed=1)
    assert updated['status'] == 'running'
    assert updated['rounds_completed'] == 1

    row2 = repo.set_cancel_requested(task_id, requested=True)
    assert row2['cancel_requested'] is True
    assert repo.is_cancel_requested(task_id) is True

    none_on_conflict = repo.update_task_status_if(
        task_id,
        expected_status='queued',
        status='failed_gate',
        reason='conflict',
    )
    assert none_on_conflict is None

    ok_on_match = repo.update_task_status_if(
        task_id,
        expected_status='running',
        status='failed_gate',
        reason='blocked',
        rounds_completed=2,
        set_cancel_requested=False,
    )
    assert ok_on_match is not None
    assert ok_on_match['status'] == 'failed_gate'
    assert ok_on_match['cancel_requested'] is False
    assert ok_on_match['rounds_completed'] == 2

    e1 = repo.append_event(task_id, event_type='discussion', payload={'x': 1}, round_number=1)
    e2 = repo.append_event(task_id, event_type=EventType.REVIEW, payload={'verdict': 'no_blocker'}, round_number=1)
    assert e1['seq'] == 1
    assert e2['seq'] == 2
    assert e2['type'] == 'review'
    events = repo.list_events(task_id)
    assert len(events) == 2

    assert repo.delete_tasks(['', task_id, task_id]) == 1
    assert repo.delete_tasks([task_id]) == 0


def test_inmemory_repository_keyerror_paths():
    repo = InMemoryTaskRepository()
    with pytest.raises(KeyError):
        repo.update_task_status('missing', status='running', reason=None)
    with pytest.raises(KeyError):
        repo.set_cancel_requested('missing', requested=True)
    with pytest.raises(KeyError):
        repo.is_cancel_requested('missing')
    with pytest.raises(KeyError):
        repo.update_task_status_if('missing', expected_status='queued', status='running', reason=None)
    with pytest.raises(KeyError):
        repo.append_event('missing', event_type='discussion', payload={}, round_number=None)
    with pytest.raises(KeyError):
        repo.list_events('missing')


def test_encode_decode_task_meta_roundtrip_and_edge_cases():
    raw = encode_task_meta(
        reviewer_participants=['claude#review-B'],
        evolution_level=9,  # clamp to 3
        evolve_until='2026-02-18T07:00:00',
        provider_models={'codex': 'gpt-5.3-codex', '': ''},
        provider_model_params={'codex': '-c model_reasoning_effort=xhigh'},
        participant_models={'codex#author-A': 'gpt-5.3-codex'},
        participant_model_params={'codex#author-A': '-c model_reasoning_effort=xhigh'},
        conversation_language='invalid-language',
        claude_team_agents=True,
        codex_multi_agents=True,
        claude_team_agents_overrides={'claude#review-B': True},
        codex_multi_agents_overrides={'codex#author-A': False},
        repair_mode='unknown',
        plain_mode='no',  # noqa: FBT003
        stream_mode='1',  # noqa: FBT003
        debate_mode='yes',  # noqa: FBT003
        auto_merge='1',  # noqa: FBT003
        merge_target_path=' C:/target ',
        sandbox_mode='1',  # noqa: FBT003
        sandbox_workspace_path=' C:/repo-lab ',
        sandbox_generated='true',  # noqa: FBT003
        sandbox_cleanup_on_pass='true',  # noqa: FBT003
        project_path='',
        self_loop_mode=99,  # clamp to 1
        workspace_fingerprint={'schema': 'workspace_fingerprint.v1', '': 'drop'},
    )
    parsed = decode_task_meta(raw)
    assert parsed['evolution_level'] == 3
    assert parsed['conversation_language'] == 'en'
    assert parsed['repair_mode'] == 'balanced'
    assert parsed['self_loop_mode'] == 1
    assert parsed['merge_target_path'] == 'C:/target'
    assert parsed['sandbox_workspace_path'] == 'C:/repo-lab'
    assert parsed['workspace_fingerprint']['schema'] == 'workspace_fingerprint.v1'

    list_form = decode_task_meta(json.dumps(['a', 'b']))
    assert list_form['participants'] == ['a', 'b']

    invalid = decode_task_meta('not-json')
    assert invalid['participants'] == []
    assert invalid['auto_merge'] is True

    weird = decode_task_meta(json.dumps({'participants': 'not-a-list', 'provider_models': 'bad'}))
    assert weird['participants'] == []
    assert weird['provider_models'] == {}

    not_dict = decode_task_meta(json.dumps('hello'))
    assert not_dict['participants'] == []


def test_encode_decode_reviewer_meta_and_bool_coercion():
    raw = encode_reviewer_meta(['claude#review-B'], 1, '2026-02-18T07:00:00')
    participants, level, until = decode_reviewer_meta(raw)
    assert participants == ['claude#review-B']
    assert level == 1
    assert until == '2026-02-18T07:00:00'

    assert _coerce_meta_bool('1', default=False) is True
    assert _coerce_meta_bool('0', default=True) is False
    assert _coerce_meta_bool('', default=True) is True
    assert _coerce_meta_bool(None, default=False) is False
    assert _coerce_meta_bool('unexpected', default=False) is True
