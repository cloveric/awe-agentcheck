from datetime import datetime
import pytest

from awe_agentcheck.automation import (
    acquire_single_instance,
    is_provider_limit_reason,
    parse_until,
    should_retry_start_for_concurrency_limit,
    should_switch_back_to_primary,
    should_switch_to_fallback,
)


def test_parse_until_supports_common_formats():
    dt = parse_until('2026-02-12 07:00')
    assert dt == datetime(2026, 2, 12, 7, 0)


def test_parse_until_supports_iso_format():
    dt = parse_until('2026-02-12T07:00:00')
    assert dt == datetime(2026, 2, 12, 7, 0, 0)


def test_should_switch_to_fallback_when_failed_system_mentions_claude():
    assert should_switch_to_fallback('failed_system', 'workflow_error: Command failed (1): claude -p') is True


def test_should_not_switch_for_non_system_failures():
    assert should_switch_to_fallback('failed_gate', 'review_blocker') is False


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


def test_should_retry_start_for_queued_concurrency_limit():
    assert should_retry_start_for_concurrency_limit('queued', 'concurrency_limit') is True
    assert should_retry_start_for_concurrency_limit('running', 'concurrency_limit') is False


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
