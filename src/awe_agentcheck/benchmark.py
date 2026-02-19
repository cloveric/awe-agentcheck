from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path


DEFAULT_BENCHMARK_TASKS: list[dict[str, str]] = [
    {
        'id': 'api-validation-hardening',
        'title': 'Benchmark: API validation hardening',
        'description': 'Audit API input validation and fix one concrete reliability bug with tests.',
    },
    {
        'id': 'task-state-transition',
        'title': 'Benchmark: task state transition reliability',
        'description': 'Inspect task start/cancel/status transitions and patch one race or stale-state issue.',
    },
    {
        'id': 'conversation-ux-readability',
        'title': 'Benchmark: conversation readability quality',
        'description': 'Improve conversation clarity by reducing noisy output and preserving key evidence paths.',
    },
    {
        'id': 'history-traceability',
        'title': 'Benchmark: project history traceability',
        'description': 'Check project history/event lineage and fix one missing or misleading trace record path.',
    },
    {
        'id': 'watchdog-stability',
        'title': 'Benchmark: watchdog stability',
        'description': 'Audit watchdog timeout/stall logic and improve one reliability edge case.',
    },
    {
        'id': 'security-guardrails',
        'title': 'Benchmark: security guardrails',
        'description': 'Review API/service guardrails for risky defaults and tighten one concrete exposure vector.',
    },
]


def load_benchmark_tasks(path: str | Path | None = None) -> list[dict[str, str]]:
    target = Path(path).resolve(strict=False) if path else None
    if target is None or not target.exists():
        return list(DEFAULT_BENCHMARK_TASKS)
    try:
        raw = target.read_text(encoding='utf-8')
        data = json.loads(raw)
    except Exception:
        return list(DEFAULT_BENCHMARK_TASKS)
    if not isinstance(data, list):
        return list(DEFAULT_BENCHMARK_TASKS)

    out: list[dict[str, str]] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        title = str(item.get('title') or '').strip()
        description = str(item.get('description') or '').strip()
        if not title or not description:
            continue
        task_id = str(item.get('id') or '').strip() or f'task-{i + 1:02d}'
        out.append({'id': task_id, 'title': title, 'description': description})
    return out or list(DEFAULT_BENCHMARK_TASKS)


def load_regression_tasks(path: str | Path | None = None) -> list[dict[str, str]]:
    target = Path(path).resolve(strict=False) if path else None
    if target is None or not target.exists():
        return []
    try:
        raw = target.read_text(encoding='utf-8')
        data = json.loads(raw)
    except Exception:
        return []
    if not isinstance(data, list):
        return []

    out: list[dict[str, str]] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        title = str(item.get('title') or '').strip()
        description = str(item.get('description') or '').strip()
        if not title or not description:
            continue
        task_id = str(item.get('id') or '').strip() or f'regression-{i + 1:02d}'
        out.append({'id': task_id, 'title': title, 'description': description})
    return out


def merge_benchmark_tasks(base: list[dict[str, str]], extras: list[dict[str, str]]) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in [*(base or []), *(extras or [])]:
        if not isinstance(item, dict):
            continue
        task_id = str(item.get('id') or '').strip()
        title = str(item.get('title') or '').strip()
        description = str(item.get('description') or '').strip()
        if not task_id or not title or not description:
            continue
        key = task_id.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append({'id': task_id, 'title': title, 'description': description})
    return merged


def summarize_benchmark_results(results: list[dict]) -> dict[str, float | int]:
    rows = list(results or [])
    total = len(rows)
    passed = sum(1 for row in rows if str(row.get('status') or '') == 'passed')
    failed_gate = sum(1 for row in rows if str(row.get('status') or '') == 'failed_gate')
    failed_system = sum(1 for row in rows if str(row.get('status') or '') == 'failed_system')
    canceled = sum(1 for row in rows if str(row.get('status') or '') == 'canceled')
    timeout_like = sum(
        1
        for row in rows
        if 'timeout' in str(row.get('reason') or '').lower() or 'watchdog' in str(row.get('reason') or '').lower()
    )

    durations = []
    for row in rows:
        try:
            value = float(row.get('duration_seconds') or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0:
            durations.append(value)
    avg_duration = (sum(durations) / len(durations)) if durations else 0.0

    return {
        'total': total,
        'passed': passed,
        'failed_gate': failed_gate,
        'failed_system': failed_system,
        'canceled': canceled,
        'timeout_like': timeout_like,
        'pass_rate': round((passed / total) if total else 0.0, 4),
        'failed_gate_rate': round((failed_gate / total) if total else 0.0, 4),
        'failed_system_rate': round((failed_system / total) if total else 0.0, 4),
        'timeout_like_rate': round((timeout_like / total) if total else 0.0, 4),
        'avg_duration_seconds': round(avg_duration, 2),
    }


def compare_benchmark_summaries(a: dict, b: dict) -> dict[str, float]:
    def val(obj: dict, key: str) -> float:
        try:
            return float(obj.get(key) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    return {
        'pass_rate_delta': round(val(b, 'pass_rate') - val(a, 'pass_rate'), 4),
        'timeout_like_rate_delta': round(val(b, 'timeout_like_rate') - val(a, 'timeout_like_rate'), 4),
        'failed_gate_rate_delta': round(val(b, 'failed_gate_rate') - val(a, 'failed_gate_rate'), 4),
        'failed_system_rate_delta': round(val(b, 'failed_system_rate') - val(a, 'failed_system_rate'), 4),
        'avg_duration_seconds_delta': round(val(b, 'avg_duration_seconds') - val(a, 'avg_duration_seconds'), 2),
    }


def build_benchmark_markdown(
    *,
    variant_a_name: str,
    variant_b_name: str,
    summary_a: dict,
    summary_b: dict,
    comparison: dict,
    generated_at: str | None = None,
) -> str:
    stamp = str(generated_at or datetime.now().isoformat())
    lines = [
        '# Benchmark A/B Report',
        '',
        f'Generated at: {stamp}',
        '',
        '## Variant A',
        f'- Name: {variant_a_name}',
        f'- Pass rate: {summary_a.get("pass_rate", 0.0)}',
        f'- Timeout-like rate: {summary_a.get("timeout_like_rate", 0.0)}',
        f'- Failed-gate rate: {summary_a.get("failed_gate_rate", 0.0)}',
        f'- Failed-system rate: {summary_a.get("failed_system_rate", 0.0)}',
        f'- Avg duration seconds: {summary_a.get("avg_duration_seconds", 0.0)}',
        '',
        '## Variant B',
        f'- Name: {variant_b_name}',
        f'- Pass rate: {summary_b.get("pass_rate", 0.0)}',
        f'- Timeout-like rate: {summary_b.get("timeout_like_rate", 0.0)}',
        f'- Failed-gate rate: {summary_b.get("failed_gate_rate", 0.0)}',
        f'- Failed-system rate: {summary_b.get("failed_system_rate", 0.0)}',
        f'- Avg duration seconds: {summary_b.get("avg_duration_seconds", 0.0)}',
        '',
        '## Delta (B - A)',
        f'- pass_rate_delta: {comparison.get("pass_rate_delta", 0.0)}',
        f'- timeout_like_rate_delta: {comparison.get("timeout_like_rate_delta", 0.0)}',
        f'- failed_gate_rate_delta: {comparison.get("failed_gate_rate_delta", 0.0)}',
        f'- failed_system_rate_delta: {comparison.get("failed_system_rate_delta", 0.0)}',
        f'- avg_duration_seconds_delta: {comparison.get("avg_duration_seconds_delta", 0.0)}',
    ]
    return '\n'.join(lines) + '\n'
