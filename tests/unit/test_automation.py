from datetime import datetime
import awe_agentcheck.automation as automation
import pytest

from awe_agentcheck.automation import (
    acquire_single_instance,
    derive_policy_adjustment_from_analytics,
    extract_self_followup_topic,
    is_provider_limit_reason,
    parse_until,
    recommend_process_followup_topic,
    summarize_actionable_text,
    should_retry_start_for_concurrency_limit,
    should_switch_back_to_primary,
    should_switch_to_fallback,
)
from awe_agentcheck.policy_templates import DEFAULT_POLICY_TEMPLATE


def test_parse_until_supports_common_formats():
    dt = parse_until('2026-02-12 07:00')
    assert dt == datetime(2026, 2, 12, 7, 0)


def test_parse_until_supports_iso_format():
    dt = parse_until('2026-02-12T07:00:00')
    assert dt == datetime(2026, 2, 12, 7, 0, 0)


def test_parse_until_rejects_empty_or_invalid():
    with pytest.raises(ValueError):
        parse_until('')
    with pytest.raises(ValueError):
        parse_until('not-a-datetime')


def test_should_switch_to_fallback_when_failed_system_mentions_claude():
    assert should_switch_to_fallback('failed_system', 'workflow_error: Command failed (1): claude -p') is True


def test_should_not_switch_for_non_system_failures():
    assert should_switch_to_fallback('failed_gate', 'review_blocker') is False


def test_should_switch_to_fallback_for_command_failed_text():
    assert should_switch_to_fallback('failed_system', 'Command failed (1): claude -p') is True


def test_should_switch_to_fallback_on_claude_command_not_found():
    assert (
        should_switch_to_fallback(
            'failed_system',
            'workflow_error: command_not_found provider=claude command=claude -p',
        )
        is True
    )


def test_should_switch_back_to_primary_on_codex_timeout():
    assert (
        should_switch_back_to_primary(
            'failed_system',
            'workflow_error: command_timeout provider=codex command=codex exec timeout_seconds=90',
        )
        is True
    )


def test_should_not_switch_back_to_primary_for_non_codex_reason():
    assert (
        should_switch_back_to_primary(
            'failed_system',
            'workflow_error: command_not_found provider=claude command=claude -p',
        )
        is False
    )


def test_should_switch_back_to_primary_on_codex_command_not_found():
    assert (
        should_switch_back_to_primary(
            'failed_system',
            'workflow_error: command_not_found provider=codex command=codex exec',
        )
        is True
    )


def test_should_not_switch_back_to_primary_when_status_not_failed_system():
    assert should_switch_back_to_primary('running', 'provider=codex command_timeout') is False


def test_should_switch_to_fallback_on_claude_provider_limit():
    assert (
        should_switch_to_fallback(
            'failed_system',
            'workflow_error: provider_limit provider=claude command=claude -p',
        )
        is True
    )


def test_should_switch_back_to_primary_on_codex_provider_limit():
    assert (
        should_switch_back_to_primary(
            'failed_system',
            'workflow_error: provider_limit provider=codex command=codex exec',
        )
        is True
    )


def test_is_provider_limit_reason_detects_provider_scoped_limit():
    reason = 'workflow_error: provider_limit provider=claude command=claude -p'
    assert is_provider_limit_reason(reason, provider='claude') is True
    assert is_provider_limit_reason(reason, provider='codex') is False


def test_is_provider_limit_reason_without_provider_filter():
    assert is_provider_limit_reason('provider_limit provider=gemini') is True
    assert is_provider_limit_reason('command_timeout provider=gemini') is False


def test_should_retry_start_for_queued_concurrency_limit():
    assert should_retry_start_for_concurrency_limit('queued', 'concurrency_limit') is True
    assert should_retry_start_for_concurrency_limit('running', 'concurrency_limit') is False


def test_recommend_process_followup_topic_for_watchdog_timeout():
    topic = recommend_process_followup_topic('failed_system', 'watchdog_timeout: task exceeded 1200s')
    assert topic is not None
    assert 'watchdog' in topic.lower()


def test_recommend_process_followup_topic_for_concurrency_limit():
    topic = recommend_process_followup_topic('queued', 'concurrency_limit')
    assert topic is not None
    assert 'concurrency' in topic.lower()


@pytest.mark.parametrize(
    ('reason', 'needle'),
    [
        ('provider_limit provider=codex', 'provider-limit'),
        ('command_timeout provider=codex', 'timeout'),
        ('command_not_found provider=codex', 'bootstrapping'),
        ('auto_merge_error', 'auto-merge'),
        ('proposal_consensus_not_reached', 'consensus'),
        ('loop_no_progress', 'loop-no-progress'),
    ],
)
def test_recommend_process_followup_topic_additional_reason_matrix(reason: str, needle: str):
    topic = recommend_process_followup_topic('failed_system', reason)
    assert topic is not None
    assert needle in topic.lower()


def test_recommend_process_followup_topic_returns_none_for_empty_inputs():
    assert recommend_process_followup_topic('', '') is None


def test_summarize_actionable_text_skips_noise_headers():
    text = (
        'OpenAI Codex v0.101.0\n'
        'VERDICT: BLOCKER\n'
        'Issue: API can deadlock when cancel races with start.\n'
    )
    summary = summarize_actionable_text(text)
    assert 'deadlock' in summary.lower()


def test_summarize_actionable_text_fallbacks_and_truncates():
    assert summarize_actionable_text(' \r\n\t ') == ''
    text = 'A' * 500
    summary = summarize_actionable_text(text, max_chars=40)
    assert summary.endswith('...')
    assert len(summary) <= 40


def test_extract_self_followup_topic_prefers_blocker_review():
    events = [
        {
            'type': 'review',
            'payload': {
                'verdict': 'blocker',
                'output': 'Issue: start/cancel transition can race and leave task stuck running.',
            },
        }
    ]
    topic = extract_self_followup_topic(events)
    assert topic is not None
    assert 'reviewer concern' in topic.lower()


def test_extract_self_followup_topic_review_gate_prefers_reviewer_summary():
    events = [
        {
            'type': 'review',
            'payload': {
                'verdict': 'blocker',
                'output': 'Issue: API can deadlock when cancel races with start.',
            },
        },
        {'type': 'gate_failed', 'payload': {'reason': 'review_blocker'}},
    ]
    topic = extract_self_followup_topic(events)
    assert topic is not None
    assert topic.lower().startswith('address reviewer concern:')
    assert 'deadlock' in topic.lower()


def test_extract_self_followup_topic_non_review_gate_stays_gate_reason():
    events = [
        {
            'type': 'review',
            'payload': {
                'verdict': 'blocker',
                'output': 'Issue: start/cancel transition can race and leave task stuck running.',
            },
        },
        {'type': 'gate_failed', 'payload': {'reason': 'tests_failed'}},
    ]
    topic = extract_self_followup_topic(events)
    assert topic is not None
    assert topic.lower().startswith('address gate failure cause:')
    assert 'tests_failed' in topic.lower()


def test_extract_self_followup_topic_review_gate_falls_back_without_summary():
    events = [
        {'type': 'review', 'payload': {'verdict': 'blocker', 'output': '   '}},
        {'type': 'gate_failed', 'payload': {'reason': 'review_blocker'}},
    ]
    topic = extract_self_followup_topic(events)
    assert topic == 'Address gate failure cause: review_blocker'


def test_extract_self_followup_topic_from_runtime_error():
    events = [
        {
            'type': 'proposal_discussion_error',
            'payload': {'reason': 'command_timeout provider=codex command=codex exec timeout_seconds=240'},
        }
    ]
    topic = extract_self_followup_topic(events)
    assert topic is not None
    assert 'runtime error' in topic.lower()


def test_extract_self_followup_topic_returns_none_when_no_signal():
    topic = extract_self_followup_topic([{'type': 'review', 'payload': {'verdict': 'no_blocker', 'output': 'ok'}}])
    assert topic is None


def test_recommend_process_followup_topic_for_precompletion_evidence_missing():
    topic = recommend_process_followup_topic('failed_gate', 'precompletion_evidence_missing')
    assert topic is not None
    assert 'evidence-path' in topic.lower()


def test_recommend_process_followup_topic_for_workspace_resume_guard_mismatch():
    topic = recommend_process_followup_topic('waiting_manual', 'workspace_resume_guard_mismatch')
    assert topic is not None
    assert 'workspace drift' in topic.lower()


def test_derive_policy_adjustment_from_analytics_timeout_cluster():
    analytics_payload = {
        'failure_taxonomy': [
            {'bucket': 'command_timeout', 'count': 8, 'share': 0.4},
            {'bucket': 'review_blocker', 'count': 2, 'share': 0.1},
        ],
        'reviewer_drift': [],
    }
    adjustment = derive_policy_adjustment_from_analytics(analytics_payload, fallback_template='balanced-default')
    assert adjustment['recommended_template'] == 'rapid-fix'
    assert adjustment['top_failure_bucket'] == 'command_timeout'
    assert adjustment['reason'] == 'stability_timeout_cluster'
    overrides = adjustment.get('task_overrides') or {}
    assert overrides.get('debate_mode') is False
    assert int(overrides.get('max_rounds') or 0) == 1


def test_derive_policy_adjustment_from_analytics_review_cluster_with_drift():
    analytics_payload = {
        'failure_taxonomy': [
            {'bucket': 'review_blocker', 'count': 5, 'share': 0.5},
        ],
        'reviewer_drift': [
            {'participant': 'claude#review-B', 'drift_score': 0.41},
        ],
    }
    adjustment = derive_policy_adjustment_from_analytics(analytics_payload, fallback_template='balanced-default')
    assert adjustment['recommended_template'] == 'safe-review'
    assert adjustment['top_failure_bucket'] == 'review_blocker'
    assert adjustment['high_drift_participant'] == 'claude#review-B'
    overrides = adjustment.get('task_overrides') or {}
    assert overrides.get('plain_mode') is True


def test_derive_policy_adjustment_from_analytics_workspace_consistency_cluster():
    analytics_payload = {
        'failure_taxonomy': [
            {'bucket': 'workspace_resume_guard_mismatch', 'count': 3, 'share': 0.3},
        ],
        'reviewer_drift': [],
    }
    adjustment = derive_policy_adjustment_from_analytics(analytics_payload, fallback_template='balanced-default')
    assert adjustment['recommended_template'] == 'safe-review'
    assert adjustment['reason'] == 'workspace_consistency_cluster'
    overrides = adjustment.get('task_overrides') or {}
    assert overrides.get('sandbox_mode') is True
    assert overrides.get('self_loop_mode') == 0


def test_derive_policy_adjustment_from_analytics_additional_clusters():
    tests_payload = {
        'failure_taxonomy': [{'bucket': 'tests_failed', 'count': 4}],
        'reviewer_drift': [],
    }
    tests_adjust = derive_policy_adjustment_from_analytics(tests_payload, fallback_template='safe-review')
    assert tests_adjust['reason'] == 'verification_failure_cluster'
    assert tests_adjust['recommended_template'] == DEFAULT_POLICY_TEMPLATE
    assert tests_adjust['task_overrides']['repair_mode'] == 'structural'

    consensus_payload = {
        'failure_taxonomy': [{'bucket': 'proposal_consensus_stalled', 'count': 4}],
        'reviewer_drift': [{'participant': 'codex#review-B', 'drift_score': 0.4}],
    }
    consensus_adjust = derive_policy_adjustment_from_analytics(consensus_payload, fallback_template='balanced-default')
    assert consensus_adjust['reason'] == 'consensus_stall_cluster'
    assert consensus_adjust['recommended_template'] == 'safe-review'
    assert consensus_adjust['task_overrides']['plain_mode'] is True

    no_signal = derive_policy_adjustment_from_analytics(None, fallback_template='safe-review')
    assert no_signal['reason'] == 'no_failure_signal'
    assert no_signal['recommended_template'] == 'safe-review'
    assert no_signal['top_failure_bucket'] == 'none'


def test_acquire_single_instance_creates_and_releases_lock(tmp_path):
    lock = tmp_path / 'overnight.lock'
    pid = 888

    with acquire_single_instance(lock, pid=pid):
        assert lock.exists() is True
        assert str(pid) in lock.read_text(encoding='utf-8')

    assert lock.exists() is False


def test_acquire_single_instance_rejects_existing_live_pid(tmp_path):
    lock = tmp_path / 'overnight.lock'
    lock.write_text('123\n', encoding='utf-8')

    with pytest.raises(RuntimeError, match='pid=123'):
        with acquire_single_instance(lock, pid=888, pid_exists=lambda p: p == 123):
            pass


def test_acquire_single_instance_reclaims_stale_lock(tmp_path):
    lock = tmp_path / 'overnight.lock'
    lock.write_text('123\n', encoding='utf-8')

    with acquire_single_instance(lock, pid=888, pid_exists=lambda p: False):
        assert lock.exists() is True
        assert lock.read_text(encoding='utf-8').startswith('888')


def test_acquire_single_instance_race_on_open_returns_stable_error(tmp_path, monkeypatch):
    lock = tmp_path / 'overnight.lock'

    def raise_file_exists(*args, **kwargs):  # noqa: ANN002, ANN003
        raise FileExistsError()

    monkeypatch.setattr(automation.os, 'open', raise_file_exists)

    with pytest.raises(RuntimeError, match='^lock already held$'):
        with acquire_single_instance(lock, pid=888, pid_exists=lambda p: False):
            pass


def test_acquire_single_instance_does_not_remove_foreign_owner_lock(tmp_path):
    lock = tmp_path / 'overnight.lock'
    lock.write_text('999\n', encoding='utf-8')

    with acquire_single_instance(lock, pid=888, pid_exists=lambda p: False):
        lock.write_text('777\n', encoding='utf-8')

    # foreign owner lock should remain untouched by pid=888 cleanup path
    assert lock.exists() is True
    assert lock.read_text(encoding='utf-8').startswith('777')


def test_pid_exists_default_non_positive_and_posix_branch(monkeypatch):
    assert automation._pid_exists_default(0) is False

    monkeypatch.setattr(automation.os, 'name', 'posix')
    monkeypatch.setattr(automation.os, 'kill', lambda _pid, _sig: None)
    assert automation._pid_exists_default(123) is True

    def _raise_oserror(_pid, _sig):
        raise OSError('missing')

    monkeypatch.setattr(automation.os, 'kill', _raise_oserror)
    assert automation._pid_exists_default(123) is False


def test_read_lock_pid_handles_missing_and_invalid(tmp_path):
    missing = tmp_path / 'missing.lock'
    assert automation._read_lock_pid(missing) is None

    invalid = tmp_path / 'invalid.lock'
    invalid.write_text('abc\n', encoding='utf-8')
    assert automation._read_lock_pid(invalid) is None

    valid = tmp_path / 'valid.lock'
    valid.write_text('42\nother\n', encoding='utf-8')
    assert automation._read_lock_pid(valid) == 42
