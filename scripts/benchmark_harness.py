from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import time

import httpx

from awe_agentcheck.benchmark import (
    build_benchmark_markdown,
    compare_benchmark_summaries,
    load_benchmark_tasks,
    load_regression_tasks,
    merge_benchmark_tasks,
    summarize_benchmark_results,
)
from awe_agentcheck.policy_templates import DEFAULT_POLICY_TEMPLATE


TERMINAL_STATUSES = {'passed', 'failed_gate', 'failed_system', 'canceled'}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Run fixed benchmark tasks for A/B orchestrator regression.')
    parser.add_argument('--api-base', default='http://127.0.0.1:8000')
    parser.add_argument('--workspace-path', default='.')
    parser.add_argument('--tasks-file', default='ops/benchmark_tasks.json')
    parser.add_argument('--regression-file', default='.agents/regressions/failure_tasks.json')
    parser.add_argument('--include-regression', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--report-dir', default='.agents/benchmarks')
    parser.add_argument('--variant-a-name', default='A')
    parser.add_argument('--variant-b-name', default='B')
    parser.add_argument('--variant-a-template', default=DEFAULT_POLICY_TEMPLATE)
    parser.add_argument('--variant-b-template', default='safe-review')
    parser.add_argument('--variant-a-overrides', default='{}', help='JSON map of task payload overrides for variant A')
    parser.add_argument('--variant-b-overrides', default='{}', help='JSON map of task payload overrides for variant B')
    parser.add_argument('--author', default='codex#author-A')
    parser.add_argument('--reviewer', action='append', default=None)
    parser.add_argument('--poll-seconds', type=int, default=5)
    parser.add_argument('--task-timeout-seconds', type=int, default=3600)
    parser.add_argument('--test-command', default='py -m pytest -q')
    parser.add_argument('--lint-command', default='py -m ruff check .')
    return parser


def parse_json_map(text: str) -> dict:
    source = str(text or '').strip()
    if not source:
        return {}
    try:
        data = json.loads(source)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def fetch_policy_defaults(client: httpx.Client, *, api_base: str, workspace_path: str) -> dict[str, dict]:
    try:
        resp = client.get(
            f'{api_base}/api/policy-templates',
            params={'workspace_path': workspace_path},
            timeout=120,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception:
        return {}
    rows = payload.get('templates') if isinstance(payload, dict) else None
    templates = rows if isinstance(rows, list) else []
    out: dict[str, dict] = {}
    for row in templates:
        if not isinstance(row, dict):
            continue
        tid = str(row.get('id') or '').strip()
        defaults = row.get('defaults')
        if tid and isinstance(defaults, dict):
            out[tid] = dict(defaults)
    return out


def wait_terminal(
    client: httpx.Client,
    *,
    api_base: str,
    task_id: str,
    poll_seconds: int,
    task_timeout_seconds: int,
) -> dict:
    started = time.monotonic()
    while True:
        resp = client.get(f'{api_base}/api/tasks/{task_id}', timeout=120)
        resp.raise_for_status()
        payload = resp.json()
        status = str(payload.get('status') or '')
        if status in TERMINAL_STATUSES:
            return payload if isinstance(payload, dict) else {}
        if task_timeout_seconds > 0 and (time.monotonic() - started) >= int(task_timeout_seconds):
            try:
                client.post(
                    f'{api_base}/api/tasks/{task_id}/force-fail',
                    json={'reason': f'benchmark_timeout: exceeded {task_timeout_seconds}s'},
                    timeout=120,
                )
            except Exception:
                pass
            return {'task_id': task_id, 'status': 'failed_system', 'last_gate_reason': 'benchmark_timeout'}
        time.sleep(max(1, int(poll_seconds)))


def parse_duration_seconds(row: dict) -> float:
    created = str(row.get('created_at') or '').strip()
    updated = str(row.get('updated_at') or '').strip()
    if not created or not updated:
        return 0.0
    try:
        a = datetime.fromisoformat(created.replace('Z', '+00:00'))
        b = datetime.fromisoformat(updated.replace('Z', '+00:00'))
    except ValueError:
        return 0.0
    delta = (b - a).total_seconds()
    return delta if delta >= 0 else 0.0


def create_task_payload(
    *,
    task_title: str,
    task_description: str,
    workspace_path: str,
    author: str,
    reviewers: list[str],
    test_command: str,
    lint_command: str,
    base_defaults: dict,
    overrides: dict,
) -> dict:
    payload = {
        'title': task_title,
        'description': task_description,
        'author_participant': author,
        'reviewer_participants': list(reviewers),
        'workspace_path': workspace_path,
        'sandbox_mode': True,
        'self_loop_mode': 0,
        'auto_merge': False,
        'debate_mode': True,
        'plain_mode': True,
        'stream_mode': True,
        'max_rounds': 1,
        'repair_mode': 'balanced',
        'evolution_level': 0,
        'test_command': test_command,
        'lint_command': lint_command,
        'auto_start': True,
    }
    payload.update(dict(base_defaults or {}))
    payload.update(dict(overrides or {}))
    payload['author_participant'] = author
    payload['reviewer_participants'] = list(reviewers)
    payload['workspace_path'] = workspace_path
    payload['test_command'] = test_command
    payload['lint_command'] = lint_command
    payload['auto_start'] = True
    return payload


def run_variant(
    client: httpx.Client,
    *,
    api_base: str,
    variant_name: str,
    tasks: list[dict[str, str]],
    payload_defaults: dict,
    payload_overrides: dict,
    workspace_path: str,
    author: str,
    reviewers: list[str],
    test_command: str,
    lint_command: str,
    poll_seconds: int,
    task_timeout_seconds: int,
) -> list[dict]:
    results: list[dict] = []
    for index, task in enumerate(tasks, start=1):
        title = str(task.get('title') or f'benchmark-{index}').strip()
        description = str(task.get('description') or title).strip()
        payload = create_task_payload(
            task_title=f'[{variant_name}] {title}',
            task_description=description,
            workspace_path=workspace_path,
            author=author,
            reviewers=reviewers,
            test_command=test_command,
            lint_command=lint_command,
            base_defaults=payload_defaults,
            overrides=payload_overrides,
        )
        create_resp = client.post(f'{api_base}/api/tasks', json=payload, timeout=120)
        create_resp.raise_for_status()
        created = create_resp.json()
        task_id = str(created.get('task_id') or '').strip()
        if not task_id:
            continue

        terminal = wait_terminal(
            client,
            api_base=api_base,
            task_id=task_id,
            poll_seconds=poll_seconds,
            task_timeout_seconds=task_timeout_seconds,
        )
        status = str(terminal.get('status') or created.get('status') or 'unknown')
        reason = str(terminal.get('last_gate_reason') or '')
        duration = parse_duration_seconds(terminal if isinstance(terminal, dict) else created)
        result = {
            'variant': variant_name,
            'task_id': task_id,
            'benchmark_id': str(task.get('id') or f'task-{index}'),
            'title': title,
            'status': status,
            'reason': reason,
            'duration_seconds': round(duration, 2),
        }
        results.append(result)
        print(
            f'[benchmark] variant={variant_name} task={task_id} '
            f'status={status} reason={reason} duration={duration:.2f}s'
        )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    api_base = str(args.api_base or '').rstrip('/')
    reviewers = list(args.reviewer) if args.reviewer else ['claude#review-B']
    tasks = load_benchmark_tasks(args.tasks_file)
    if bool(args.include_regression):
        regression_tasks = load_regression_tasks(args.regression_file)
        tasks = merge_benchmark_tasks(tasks, regression_tasks)
    if not tasks:
        print('[benchmark] no tasks loaded')
        return 2

    variant_a_overrides = parse_json_map(args.variant_a_overrides)
    variant_b_overrides = parse_json_map(args.variant_b_overrides)
    report_root = Path(args.report_dir)
    report_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')

    with httpx.Client(headers={'Connection': 'close'}, timeout=120) as client:
        policy_defaults = fetch_policy_defaults(
            client,
            api_base=api_base,
            workspace_path=args.workspace_path,
        )
        defaults_a = dict(policy_defaults.get(str(args.variant_a_template), {}))
        defaults_b = dict(policy_defaults.get(str(args.variant_b_template), {}))

        results_a = run_variant(
            client,
            api_base=api_base,
            variant_name=args.variant_a_name,
            tasks=tasks,
            payload_defaults=defaults_a,
            payload_overrides=variant_a_overrides,
            workspace_path=args.workspace_path,
            author=args.author,
            reviewers=reviewers,
            test_command=args.test_command,
            lint_command=args.lint_command,
            poll_seconds=max(1, int(args.poll_seconds)),
            task_timeout_seconds=max(60, int(args.task_timeout_seconds)),
        )
        results_b = run_variant(
            client,
            api_base=api_base,
            variant_name=args.variant_b_name,
            tasks=tasks,
            payload_defaults=defaults_b,
            payload_overrides=variant_b_overrides,
            workspace_path=args.workspace_path,
            author=args.author,
            reviewers=reviewers,
            test_command=args.test_command,
            lint_command=args.lint_command,
            poll_seconds=max(1, int(args.poll_seconds)),
            task_timeout_seconds=max(60, int(args.task_timeout_seconds)),
        )

    summary_a = summarize_benchmark_results(results_a)
    summary_b = summarize_benchmark_results(results_b)
    comparison = compare_benchmark_summaries(summary_a, summary_b)
    report_payload = {
        'generated_at': datetime.now().isoformat(),
        'workspace_path': str(args.workspace_path),
        'tasks_file': str(args.tasks_file),
        'regression_file': str(args.regression_file),
        'include_regression': bool(args.include_regression),
        'tasks_total': len(tasks),
        'variant_a': {
            'name': args.variant_a_name,
            'template': args.variant_a_template,
            'overrides': variant_a_overrides,
            'results': results_a,
            'summary': summary_a,
        },
        'variant_b': {
            'name': args.variant_b_name,
            'template': args.variant_b_template,
            'overrides': variant_b_overrides,
            'results': results_b,
            'summary': summary_b,
        },
        'comparison': comparison,
    }
    json_path = report_root / f'benchmark-{stamp}.json'
    md_path = report_root / f'benchmark-{stamp}.md'
    json_path.write_text(json.dumps(report_payload, ensure_ascii=True, indent=2), encoding='utf-8')
    md_path.write_text(
        build_benchmark_markdown(
            variant_a_name=args.variant_a_name,
            variant_b_name=args.variant_b_name,
            summary_a=summary_a,
            summary_b=summary_b,
            comparison=comparison,
            generated_at=report_payload['generated_at'],
        ),
        encoding='utf-8',
    )
    print(f'[benchmark] report_json={json_path}')
    print(f'[benchmark] report_md={md_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
