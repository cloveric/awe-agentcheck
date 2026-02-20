from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from awe_agentcheck.adapters.runner import ParticipantRunner
from awe_agentcheck.participants import Participant, set_extra_providers


def test_runner_handles_command_not_configured_for_supported_extra_provider(tmp_path: Path):
    set_extra_providers({'qwen'})
    try:
        runner = ParticipantRunner(command_overrides={'': '', 'qwen': ''}, dry_run=False)
        participant = Participant(participant_id='qwen#review-A', provider='qwen', alias='review-A')
        result = runner.run(
            participant=participant,
            prompt='hello',
            cwd=tmp_path,
            timeout_seconds=1,
        )
        assert result.returncode == 2
        assert 'command_not_configured provider=qwen' in result.output
    finally:
        set_extra_providers(set())


def test_runner_returns_command_failed_when_subprocess_exits_non_zero(tmp_path: Path, monkeypatch):
    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=['claude'], returncode=9, stdout='partial output', stderr='stacktrace')

    monkeypatch.setattr('awe_agentcheck.adapters.runner.subprocess.run', fake_run)
    runner = ParticipantRunner(command_overrides={'claude': 'claude -p'}, dry_run=False)
    result = runner.run(
        participant=Participant(participant_id='claude#author-A', provider='claude', alias='author-A'),
        prompt='hello',
        cwd=tmp_path,
        timeout_seconds=1,
    )
    assert result.returncode == 2
    assert 'command_failed provider=claude' in result.output


def test_runner_static_helpers_cover_edge_cases(tmp_path: Path, monkeypatch):
    assert ParticipantRunner._compute_attempt_timeout_seconds(remaining_budget=0.0, attempts_left=2) == 0.0
    assert ParticipantRunner._is_provider_limit_output('') is False
    assert ParticipantRunner._runtime_error_result(reason='', duration_seconds=-3).duration_seconds == 0.0
    assert ParticipantRunner._clip_prompt_for_retry('short') == 'short'
    assert ParticipantRunner._split_extra_args('') == []
    assert ParticipantRunner._has_model_flag(['--model', 'x']) is True
    assert ParticipantRunner._has_agents_flag(['--agents', '{}']) is True
    assert ParticipantRunner._has_codex_multi_agent_flag(['--enable', 'multi_agent']) is True
    assert ParticipantRunner._has_codex_multi_agent_config_token('features.multi_agent=true') is True
    assert ParticipantRunner._has_prompt_flag(['--prompt', 'x']) is True
    assert '--yolo' not in ParticipantRunner._normalize_gemini_approval_flags(['gemini', '--yolo', '--approval-mode', 'yolo'])
    assert ParticipantRunner._format_command(['a', 'b', 'c']) == 'a b c'
    assert ParticipantRunner._resolve_executable([]) == []
    assert ParticipantRunner._resolve_executable(['  ']) == ['  ']

    monkeypatch.setattr('awe_agentcheck.adapters.runner.shutil.which', lambda _x: None)
    assert ParticipantRunner._resolve_executable(['cmd', '--x']) == ['cmd', '--x']

    normalized = ParticipantRunner._normalize_output_for_provider(
        provider='codex',
        output='ok\nOpenAI Codex v0.1\nfooter',
    )
    assert normalized == 'ok'
    assert ParticipantRunner._normalize_codex_exec_output('intro\ncodex\nvalue\ntokens used: 1') == 'value'

    built = ParticipantRunner._build_argv(
        command='gemini --yolo',
        provider='gemini',
        provider_spec={
            'model_flag': '-m',
            'capabilities': {'claude_team_agents': False, 'codex_multi_agents': False},
        },
        model='gemini-3-pro-preview',
        model_params=None,
        claude_team_agents=False,
        codex_multi_agents=False,
    )
    assert '-m' in built
    runtime_argv, runtime_input = ParticipantRunner._prepare_runtime_invocation(
        argv=built,
        provider='gemini',
        prompt='review please',
    )
    assert '--prompt' in runtime_argv
    assert runtime_input == ''

    env_no_src = ParticipantRunner._build_subprocess_env(tmp_path)
    assert isinstance(env_no_src, dict)
    assert 'PYTHONPATH' in env_no_src or 'PYTHONPATH' not in env_no_src

    src_dir = tmp_path / 'src'
    src_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('PYTHONPATH', os.pathsep.join([str(src_dir), str(tmp_path / 'vendor')]))
    env_with_src = ParticipantRunner._build_subprocess_env(tmp_path)
    py_path = str(env_with_src.get('PYTHONPATH') or '')
    parts = [p for p in py_path.split(os.pathsep) if p]
    assert parts and Path(parts[0]).resolve(strict=False) == src_dir.resolve(strict=False)


def test_run_streaming_success_and_timeout(tmp_path: Path):
    script = tmp_path / 'stream.py'
    script.write_text(
        'import sys, time\n'
        'data = sys.stdin.read().strip()\n'
        'print(f"OUT:{data}")\n'
        'print("ERR:warn", file=sys.stderr)\n'
        'sys.stdout.flush(); sys.stderr.flush()\n',
        encoding='utf-8',
    )

    streamed: list[tuple[str, str]] = []
    result = ParticipantRunner._run_streaming(
        argv=[sys.executable, str(script)],
        runtime_input='payload',
        cwd=tmp_path,
        timeout_seconds=2.0,
        on_stream=lambda stream, chunk: streamed.append((stream, chunk)),
    )
    assert result.returncode == 0
    assert 'OUT:payload' in result.stdout
    assert 'ERR:warn' in result.stderr
    assert any(name == 'stdout' for name, _ in streamed)
    assert any(name == 'stderr' for name, _ in streamed)

    sleep_script = tmp_path / 'sleep.py'
    sleep_script.write_text(
        'import time\n'
        'time.sleep(0.5)\n'
        'print("done")\n',
        encoding='utf-8',
    )
    with pytest.raises(subprocess.TimeoutExpired):
        ParticipantRunner._run_streaming(
            argv=[sys.executable, str(sleep_script)],
            runtime_input='',
            cwd=tmp_path,
            timeout_seconds=0.05,
            on_stream=lambda _stream, _chunk: None,
        )
