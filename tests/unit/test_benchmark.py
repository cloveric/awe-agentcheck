from __future__ import annotations

import json
from pathlib import Path

from awe_agentcheck.benchmark import (
    build_benchmark_markdown,
    compare_benchmark_summaries,
    load_benchmark_tasks,
    summarize_benchmark_results,
)


def test_load_benchmark_tasks_uses_defaults_when_file_missing(tmp_path: Path):
    tasks = load_benchmark_tasks(tmp_path / 'missing.json')
    assert tasks
    assert all(str(item.get('title') or '').strip() for item in tasks)


def test_load_benchmark_tasks_reads_valid_json(tmp_path: Path):
    payload = [
        {'id': 't1', 'title': 'Task One', 'description': 'Desc one'},
        {'id': 't2', 'title': 'Task Two', 'description': 'Desc two'},
    ]
    target = tmp_path / 'tasks.json'
    target.write_text(json.dumps(payload), encoding='utf-8')
    tasks = load_benchmark_tasks(target)
    assert len(tasks) == 2
    assert tasks[0]['id'] == 't1'
    assert tasks[1]['title'] == 'Task Two'


def test_summarize_benchmark_results_calculates_rates():
    rows = [
        {'status': 'passed', 'reason': 'passed', 'duration_seconds': 10},
        {'status': 'failed_gate', 'reason': 'review_blocker', 'duration_seconds': 20},
        {'status': 'failed_system', 'reason': 'command_timeout provider=codex', 'duration_seconds': 30},
        {'status': 'canceled', 'reason': 'watchdog_timeout', 'duration_seconds': 0},
    ]
    summary = summarize_benchmark_results(rows)
    assert summary['total'] == 4
    assert summary['passed'] == 1
    assert summary['failed_gate'] == 1
    assert summary['failed_system'] == 1
    assert summary['canceled'] == 1
    assert summary['timeout_like'] == 2
    assert float(summary['pass_rate']) == 0.25


def test_compare_benchmark_summaries_returns_delta():
    a = {'pass_rate': 0.2, 'timeout_like_rate': 0.3, 'failed_gate_rate': 0.4, 'failed_system_rate': 0.1, 'avg_duration_seconds': 15}
    b = {'pass_rate': 0.4, 'timeout_like_rate': 0.2, 'failed_gate_rate': 0.2, 'failed_system_rate': 0.1, 'avg_duration_seconds': 12}
    delta = compare_benchmark_summaries(a, b)
    assert delta['pass_rate_delta'] == 0.2
    assert delta['timeout_like_rate_delta'] == -0.1
    assert delta['failed_gate_rate_delta'] == -0.2
    assert delta['avg_duration_seconds_delta'] == -3.0


def test_build_benchmark_markdown_contains_sections():
    summary_a = {'pass_rate': 0.3, 'timeout_like_rate': 0.2, 'failed_gate_rate': 0.4, 'failed_system_rate': 0.1, 'avg_duration_seconds': 14.2}
    summary_b = {'pass_rate': 0.5, 'timeout_like_rate': 0.1, 'failed_gate_rate': 0.3, 'failed_system_rate': 0.1, 'avg_duration_seconds': 12.1}
    comparison = {'pass_rate_delta': 0.2, 'timeout_like_rate_delta': -0.1, 'failed_gate_rate_delta': -0.1, 'failed_system_rate_delta': 0.0, 'avg_duration_seconds_delta': -2.1}
    md = build_benchmark_markdown(
        variant_a_name='A',
        variant_b_name='B',
        summary_a=summary_a,
        summary_b=summary_b,
        comparison=comparison,
        generated_at='2026-02-19T10:00:00',
    )
    assert '# Benchmark A/B Report' in md
    assert '## Variant A' in md
    assert '## Variant B' in md
    assert '## Delta (B - A)' in md
