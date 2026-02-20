from __future__ import annotations

import json
from pathlib import Path

from awe_agentcheck.benchmark import (
    build_benchmark_markdown,
    compare_benchmark_summaries,
    load_benchmark_tasks,
    load_regression_tasks,
    merge_benchmark_tasks,
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


def test_load_benchmark_tasks_fallback_on_invalid_payload(tmp_path: Path):
    target = tmp_path / 'tasks.json'
    target.write_text('not-json', encoding='utf-8')
    fallback = load_benchmark_tasks(target)
    assert fallback
    target.write_text(json.dumps({'not': 'a-list'}), encoding='utf-8')
    fallback2 = load_benchmark_tasks(target)
    assert fallback2


def test_load_benchmark_tasks_skips_invalid_rows_and_generates_default_id(tmp_path: Path):
    payload = [
        {'title': 'Task One', 'description': 'Desc one'},
        {'id': 'bad', 'title': '', 'description': 'desc'},
        {'id': 't3', 'title': 'Task Three', 'description': 'Desc three'},
        'not-a-dict',
    ]
    target = tmp_path / 'tasks.json'
    target.write_text(json.dumps(payload), encoding='utf-8')
    tasks = load_benchmark_tasks(target)
    assert len(tasks) == 2
    assert tasks[0]['id'] == 'task-01'
    assert tasks[1]['id'] == 't3'


def test_load_regression_tasks_reads_valid_json(tmp_path: Path):
    payload = [
        {'id': 'failure-a', 'title': 'Regression A', 'description': 'Fix reason A'},
        {'id': 'failure-b', 'title': 'Regression B', 'description': 'Fix reason B'},
    ]
    target = tmp_path / 'failure_tasks.json'
    target.write_text(json.dumps(payload), encoding='utf-8')
    tasks = load_regression_tasks(target)
    assert len(tasks) == 2
    assert tasks[0]['id'] == 'failure-a'
    assert tasks[1]['title'] == 'Regression B'


def test_load_regression_tasks_skips_invalid_rows_safely(tmp_path: Path):
    payload = [
        {'id': 'failure-a', 'title': 'Regression A', 'description': 'Fix reason A'},
        {'id': 'bad-no-description', 'title': 'Missing description'},
        'not-a-dict',
        {'id': '', 'title': 'Regression B', 'description': 'Fix reason B'},
    ]
    target = tmp_path / 'failure_tasks.json'
    target.write_text(json.dumps(payload), encoding='utf-8')
    tasks = load_regression_tasks(target)
    assert len(tasks) == 2
    assert tasks[0]['id'] == 'failure-a'
    assert tasks[1]['title'] == 'Regression B'


def test_load_regression_tasks_fallback_for_missing_or_invalid(tmp_path: Path):
    assert load_regression_tasks(tmp_path / 'missing.json') == []
    target = tmp_path / 'bad.json'
    target.write_text('not-json', encoding='utf-8')
    assert load_regression_tasks(target) == []
    target.write_text(json.dumps({'x': 1}), encoding='utf-8')
    assert load_regression_tasks(target) == []


def test_merge_benchmark_tasks_dedupes_by_id():
    merged = merge_benchmark_tasks(
        [
            {'id': 'a', 'title': 'A', 'description': 'desc-a'},
            {'id': 'b', 'title': 'B', 'description': 'desc-b'},
        ],
        [
            {'id': 'B', 'title': 'B2', 'description': 'desc-b2'},
            {'id': 'c', 'title': 'C', 'description': 'desc-c'},
        ],
    )
    assert [item['id'] for item in merged] == ['a', 'b', 'c']


def test_merge_benchmark_tasks_skips_invalid_items():
    merged = merge_benchmark_tasks(
        [{'id': 'a', 'title': 'A', 'description': 'desc-a'}],
        [{'id': '', 'title': 'X', 'description': 'desc'}, {'id': 'b', 'title': '', 'description': 'desc'}, 'bad'],
    )
    assert merged == [{'id': 'a', 'title': 'A', 'description': 'desc-a'}]


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


def test_summarize_benchmark_results_handles_empty_and_invalid_duration():
    summary = summarize_benchmark_results([])
    assert summary['total'] == 0
    assert summary['pass_rate'] == 0.0
    rows = [{'status': 'passed', 'reason': 'ok', 'duration_seconds': 'bad'}]
    summary2 = summarize_benchmark_results(rows)
    assert summary2['avg_duration_seconds'] == 0.0


def test_compare_benchmark_summaries_returns_delta():
    a = {'pass_rate': 0.2, 'timeout_like_rate': 0.3, 'failed_gate_rate': 0.4, 'failed_system_rate': 0.1, 'avg_duration_seconds': 15}
    b = {'pass_rate': 0.4, 'timeout_like_rate': 0.2, 'failed_gate_rate': 0.2, 'failed_system_rate': 0.1, 'avg_duration_seconds': 12}
    delta = compare_benchmark_summaries(a, b)
    assert delta['pass_rate_delta'] == 0.2
    assert delta['timeout_like_rate_delta'] == -0.1
    assert delta['failed_gate_rate_delta'] == -0.2
    assert delta['avg_duration_seconds_delta'] == -3.0


def test_compare_benchmark_summaries_handles_invalid_values():
    delta = compare_benchmark_summaries({'pass_rate': 'bad'}, {'pass_rate': 0.5})
    assert delta['pass_rate_delta'] == 0.5


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


def test_build_benchmark_markdown_uses_runtime_timestamp_when_missing():
    md = build_benchmark_markdown(
        variant_a_name='A',
        variant_b_name='B',
        summary_a={},
        summary_b={},
        comparison={},
        generated_at=None,
    )
    assert 'Generated at:' in md
