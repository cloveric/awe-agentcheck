from __future__ import annotations

from pathlib import Path

from awe_agentcheck.adapters import AdapterResult
from awe_agentcheck.participants import parse_participant_id
from awe_agentcheck.workflow import CommandResult, RunConfig, WorkflowEngine


class _Runner:
    def __init__(self):
        self.calls = 0

    def run(self, *, participant, prompt, cwd, timeout_seconds=900, **kwargs):
        _ = prompt
        _ = cwd
        _ = timeout_seconds
        _ = kwargs
        self.calls += 1
        # discussion + implementation pass; reviewer returns runtime-error payload.
        if participant.participant_id.endswith('#review-B'):
            return AdapterResult(
                output='provider_limit provider=claude command=claude -p',
                verdict='unknown',
                next_action='stop',
                returncode=2,
                duration_seconds=0.1,
            )
        return AdapterResult(
            output='{"verdict":"NO_BLOCKER","next_action":"pass"}\nEvidence:\n- src/awe_agentcheck/service.py',
            verdict='no_blocker',
            next_action='pass',
            returncode=0,
            duration_seconds=0.1,
        )


class _Executor:
    def run(self, command: str, cwd: Path, timeout_seconds: int) -> CommandResult:
        _ = command
        _ = cwd
        _ = timeout_seconds
        return CommandResult(ok=True, command='ok', returncode=0, stdout='', stderr='')


def test_workflow_review_runtime_reason_branch_emits_review_error(tmp_path: Path):
    runner = _Runner()
    sink: list[dict] = []
    engine = WorkflowEngine(runner=runner, command_executor=_Executor(), workflow_backend='classic')
    result = engine.run(
        RunConfig(
            task_id='task-review-runtime',
            title='Review runtime branch',
            description='exercise review runtime error path',
            author=parse_participant_id('codex#author-A'),
            reviewers=[parse_participant_id('claude#review-B')],
            evolution_level=0,
            evolve_until=None,
            cwd=tmp_path,
            max_rounds=1,
            test_command='py -m pytest -q',
            lint_command='py -m ruff check .',
        ),
        on_event=lambda event: sink.append(dict(event)),
    )

    assert result.status == 'failed_gate'
    assert result.gate_reason == 'review_unknown'
    review_errors = [e for e in sink if e.get('type') == 'review_error']
    assert review_errors
    assert review_errors[-1].get('reason') == 'provider_limit'
    review_events = [e for e in sink if e.get('type') == 'review']
    assert review_events
    assert review_events[-1].get('verdict') == 'unknown'
    assert '[review_error]' in str(review_events[-1].get('output') or '')
