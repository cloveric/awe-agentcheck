from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
import sys
import time
from pathlib import Path

import httpx

from awe_agentcheck.automation import (
    acquire_single_instance,
    is_provider_limit_reason,
    parse_until,
    should_retry_start_for_concurrency_limit,
    should_switch_back_to_primary,
    should_switch_to_fallback,
)


TERMINAL_STATUSES = {'passed', 'failed_gate', 'failed_system', 'canceled'}


@dataclass
class ParticipantPlan:
    author: str
    reviewers: list[str]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Run continuous overnight self-evolution tasks against awe-agentcheck API.')
    parser.add_argument('--api-base', default='http://127.0.0.1:8000')
    parser.add_argument('--until', required=True, help='Local datetime, e.g. "2026-02-12 07:00"')
    parser.add_argument('--workspace-path', default='C:/Users/hangw/awe-agentcheck')
    parser.add_argument('--sandbox-mode', type=int, default=1, choices=[0, 1])
    parser.add_argument('--sandbox-workspace-path', default='')
    parser.add_argument('--self-loop-mode', type=int, default=1, choices=[0, 1])
    parser.add_argument('--auto-merge', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--merge-target-path', default='')
    parser.add_argument('--author', default='claude#author-A')
    parser.add_argument('--reviewer', action='append', default=None)
    parser.add_argument('--fallback-author', default='codex#author-A')
    parser.add_argument('--fallback-reviewer', action='append', default=None)
    parser.add_argument('--evolution-level', type=int, default=0)
    parser.add_argument('--evolve-until', default='')
    parser.add_argument('--max-rounds', type=int, default=3)
    parser.add_argument('--poll-seconds', type=int, default=5)
    parser.add_argument('--idle-seconds', type=int, default=5)
    parser.add_argument('--task-timeout-seconds', type=int, default=1800)
    parser.add_argument('--max-consecutive-system-failures', type=int, default=5)
    parser.add_argument('--cooldown-seconds', type=int, default=45)
    parser.add_argument('--primary-disable-seconds', type=int, default=3600)
    parser.add_argument('--test-command', default='py -m pytest -q')
    parser.add_argument('--lint-command', default='py -m ruff check .')
    parser.add_argument('--topic-file', default='')
    parser.add_argument('--log-dir', default='C:/Users/hangw/awe-agentcheck/.agents/overnight')
    parser.add_argument('--lock-file', default='C:/Users/hangw/awe-agentcheck/.agents/overnight/overnight.lock')
    return parser


def load_topics(path: str) -> list[str]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    lines = [line.strip() for line in p.read_text(encoding='utf-8').splitlines()]
    return [line for line in lines if line and not line.startswith('#')]


def ensure_log_file(log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    path = log_dir / f'overnight-{stamp}.md'
    header = (
        '# Overnight Auto-Evolve Log\n\n'
        f'Started: {datetime.now().isoformat()}\n\n'
        '| Iteration | Task ID | Status | Rounds | Reason | Participants |\n'
        '|---|---|---|---|---|---|\n'
    )
    path.write_text(header, encoding='utf-8')
    return path


def append_log(path: Path, *, iteration: int, task_id: str, status: str, rounds: int, reason: str | None, participants: ParticipantPlan) -> None:
    row = (
        f'| {iteration} | {task_id} | {status} | {rounds} | {(reason or "")[:140]} '
        f'| {participants.author} -> {", ".join(participants.reviewers)} |\n'
    )
    with path.open('a', encoding='utf-8') as f:
        f.write(row)


def create_task(
    client: httpx.Client,
    *,
    api_base: str,
    topic: str,
    workspace_path: str,
    sandbox_mode: int,
    sandbox_workspace_path: str | None,
    self_loop_mode: int,
    auto_merge: bool,
    merge_target_path: str | None,
    participants: ParticipantPlan,
    evolution_level: int,
    evolve_until: str | None,
    max_rounds: int,
    test_command: str,
    lint_command: str,
) -> dict:
    payload = {
        'title': f'AutoEvolve: {topic[:90]}',
        'description': (
            'You are in continuous self-improvement mode. '\
            'Find one concrete improvement, implement, review, and verify.'
        ),
        'author_participant': participants.author,
        'reviewer_participants': participants.reviewers,
        'evolution_level': int(max(0, min(2, int(evolution_level)))),
        'evolve_until': (str(evolve_until).strip() if evolve_until else None),
        'workspace_path': workspace_path,
        'sandbox_mode': int(sandbox_mode) == 1,
        'sandbox_workspace_path': (str(sandbox_workspace_path).strip() if sandbox_workspace_path else None),
        'self_loop_mode': int(max(0, min(1, int(self_loop_mode)))),
        'auto_merge': bool(auto_merge),
        'merge_target_path': (str(merge_target_path).strip() if merge_target_path else None),
        'max_rounds': max_rounds,
        'test_command': test_command,
        'lint_command': lint_command,
        'auto_start': True,
    }
    resp = client.post(f'{api_base}/api/tasks', json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()


def force_fail_for_watchdog_timeout(
    client: httpx.Client,
    *,
    api_base: str,
    task_id: str,
    timeout_seconds: int,
) -> dict | None:
    reason = f'watchdog_timeout: task exceeded {timeout_seconds}s without terminal status'
    try:
        client.post(
            f'{api_base}/api/tasks/{task_id}/cancel',
            timeout=120,
        )
    except Exception:
        pass
    try:
        resp = client.post(
            f'{api_base}/api/tasks/{task_id}/force-fail',
            json={'reason': reason},
            timeout=120,
        )
        if resp.status_code < 400:
            return resp.json()
    except Exception:
        pass
    return None


def wait_terminal(
    client: httpx.Client,
    *,
    api_base: str,
    task_id: str,
    poll_seconds: int,
    task_timeout_seconds: int,
) -> dict:
    timeout_window = max(0, int(task_timeout_seconds))
    started_at = time.monotonic()
    watchdog_last_attempt = 0.0
    while True:
        now = time.monotonic()
        if timeout_window > 0 and (now - started_at) >= timeout_window and (now - watchdog_last_attempt) >= max(1, poll_seconds):
            watchdog_last_attempt = now
            forced = force_fail_for_watchdog_timeout(
                client,
                api_base=api_base,
                task_id=task_id,
                timeout_seconds=timeout_window,
            )
            if forced is not None:
                return forced

        try:
            resp = client.get(f'{api_base}/api/tasks/{task_id}', timeout=120)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError:
            time.sleep(max(1, poll_seconds))
            continue
        status = str(data.get('status', ''))
        reason = data.get('last_gate_reason')
        if should_retry_start_for_concurrency_limit(status, reason):
            try:
                client.post(
                    f'{api_base}/api/tasks/{task_id}/start',
                    json={'background': True},
                    timeout=120,
                )
            except Exception:
                pass
            time.sleep(max(1, poll_seconds))
            continue
        if data.get('status') in TERMINAL_STATUSES:
            return data
        time.sleep(max(1, poll_seconds))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    deadline = parse_until(args.until)
    topics = load_topics(args.topic_file)
    if not topics:
        topics = [
            'Improve reliability of task start/cancel transitions',
            'Refine API validation and error messages',
            'Increase observability signal quality in workflow traces',
            'Improve web panel operator ergonomics and event replay clarity',
            'Find and fix one bug in service or repository layer',
        ]

    api_base = args.api_base.rstrip('/')
    log_path = ensure_log_file(Path(args.log_dir))

    primary_reviewers = list(args.reviewer) if args.reviewer else ['codex#review-B']
    fallback_reviewers = list(args.fallback_reviewer) if args.fallback_reviewer else ['codex#review-B']

    primary = ParticipantPlan(author=args.author, reviewers=primary_reviewers)
    fallback = ParticipantPlan(author=args.fallback_author, reviewers=fallback_reviewers)
    active = primary
    consecutive_system_failures = 0
    primary_disabled_until: datetime | None = None

    print(f'[overnight] running until {deadline.isoformat()}')
    print(f'[overnight] log file: {log_path}')
    print(f'[overnight] lock file: {args.lock_file}')

    iteration = 0
    topic_index = 0
    try:
        with acquire_single_instance(Path(args.lock_file)):
            transport = httpx.HTTPTransport(retries=1)
            with httpx.Client(transport=transport, headers={'Connection': 'close'}) as client:
                while datetime.now() < deadline:
                    if primary_disabled_until and datetime.now() >= primary_disabled_until:
                        print('[overnight] primary participant cooldown expired')
                        primary_disabled_until = None

                    if active == primary and primary_disabled_until and datetime.now() < primary_disabled_until:
                        active = fallback

                    iteration += 1
                    topic = topics[topic_index % len(topics)]
                    topic_index += 1

                    try:
                        current_task_id = 'n/a'
                        created = create_task(
                            client,
                            api_base=api_base,
                            topic=topic,
                            workspace_path=args.workspace_path,
                            sandbox_mode=args.sandbox_mode,
                            sandbox_workspace_path=(args.sandbox_workspace_path.strip() or None),
                            self_loop_mode=args.self_loop_mode,
                            auto_merge=bool(args.auto_merge),
                            merge_target_path=(args.merge_target_path.strip() or None),
                            participants=active,
                            evolution_level=args.evolution_level,
                            evolve_until=(args.evolve_until.strip() or None),
                            max_rounds=args.max_rounds,
                            test_command=args.test_command,
                            lint_command=args.lint_command,
                        )
                        task_id = created['task_id']
                        current_task_id = task_id
                        print(f'[overnight] iteration={iteration} task={task_id} created')

                        final_state = wait_terminal(
                            client,
                            api_base=api_base,
                            task_id=task_id,
                            poll_seconds=args.poll_seconds,
                            task_timeout_seconds=args.task_timeout_seconds,
                        )
                        status = str(final_state.get('status', 'unknown'))
                        reason = final_state.get('last_gate_reason')
                        rounds = int(final_state.get('rounds_completed') or 0)
                        append_log(
                            log_path,
                            iteration=iteration,
                            task_id=task_id,
                            status=status,
                            rounds=rounds,
                            reason=reason,
                            participants=active,
                        )
                        print(f'[overnight] task={task_id} status={status} rounds={rounds} reason={reason}')

                        if should_switch_to_fallback(status, reason):
                            active = fallback
                            print('[overnight] switched to fallback participants due to system failure signal')
                            if is_provider_limit_reason(reason, provider='claude'):
                                primary_disabled_until = datetime.now() + timedelta(seconds=max(60, int(args.primary_disable_seconds)))
                                print(
                                    '[overnight] primary participants temporarily disabled until '
                                    f'{primary_disabled_until.isoformat()} due to claude provider_limit'
                                )
                        elif should_switch_back_to_primary(status, reason):
                            if primary_disabled_until and datetime.now() < primary_disabled_until:
                                print('[overnight] primary still in cooldown window, staying on fallback participants')
                            else:
                                active = primary
                                print('[overnight] switched back to primary participants due to codex failure signal')

                        if status == 'failed_system':
                            consecutive_system_failures += 1
                        else:
                            consecutive_system_failures = 0

                        if consecutive_system_failures >= max(1, int(args.max_consecutive_system_failures)):
                            print(
                                f'[overnight] cooling down for {args.cooldown_seconds}s after '
                                f'{consecutive_system_failures} consecutive system failures'
                            )
                            time.sleep(max(1, int(args.cooldown_seconds)))
                            consecutive_system_failures = 0

                    except Exception as exc:
                        print(f'[overnight] iteration={iteration} error={exc}', file=sys.stderr)
                        append_log(
                            log_path,
                            iteration=iteration,
                            task_id=current_task_id,
                            status='driver_error',
                            rounds=0,
                            reason=str(exc),
                            participants=active,
                        )
                        if 'claude' in str(exc).lower():
                            active = fallback
                            print('[overnight] switched to fallback participants due to claude-related error')
                            if is_provider_limit_reason(str(exc), provider='claude'):
                                primary_disabled_until = datetime.now() + timedelta(seconds=max(60, int(args.primary_disable_seconds)))
                                print(
                                    '[overnight] primary participants temporarily disabled until '
                                    f'{primary_disabled_until.isoformat()} due to claude provider_limit'
                                )
                        elif 'codex' in str(exc).lower():
                            if primary_disabled_until and datetime.now() < primary_disabled_until:
                                print('[overnight] primary still in cooldown window, staying on fallback participants')
                            else:
                                active = primary
                                print('[overnight] switched back to primary participants due to codex-related error')

                    time.sleep(max(1, args.idle_seconds))
    except RuntimeError as exc:
        print(f'[overnight] {exc}', file=sys.stderr)
        return 2

    print('[overnight] completed')
    print(f'[overnight] results: {log_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
