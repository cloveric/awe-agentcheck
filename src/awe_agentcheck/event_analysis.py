from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Pattern

from awe_agentcheck.domain.events import EventType
from awe_agentcheck.domain.models import ReviewVerdict, TaskStatus


def is_path_within(base: Path, target: Path) -> bool:
    try:
        target.relative_to(base)
        return True
    except ValueError:
        return False


def validate_artifact_task_id(task_id: str, *, pattern: Pattern[str]) -> str:
    key = str(task_id or '').strip()
    if not key:
        raise ValueError('task_id is required')
    if '..' in key or '/' in key or '\\' in key:
        raise ValueError('invalid task_id')
    if not pattern.fullmatch(key):
        raise ValueError('invalid task_id')
    return key


def normalize_history_events(*, task_id: str, events: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    next_seq = 1
    for raw in events:
        if not isinstance(raw, dict):
            continue

        seq_raw = raw.get('seq')
        try:
            seq_value = int(str(seq_raw))
        except (TypeError, ValueError):
            seq_value = next_seq
        if seq_value < 1:
            seq_value = next_seq

        payload_raw = raw.get('payload') if isinstance(raw.get('payload'), dict) else {}
        payload = dict(payload_raw) if isinstance(payload_raw, dict) else {}
        for key in (
            'output',
            'reason',
            'verdict',
            'participant',
            'provider',
            'stage',
            'mode',
            'changed_files',
            'copied_files',
            'deleted_files',
            'snapshot_path',
            'changelog_path',
            'merged_at',
        ):
            if key not in payload and key in raw:
                payload[key] = raw.get(key)

        round_raw = raw.get('round')
        try:
            round_number = int(round_raw) if round_raw is not None else None
        except (TypeError, ValueError):
            round_number = None

        created_at = str(raw.get('created_at') or '').strip() or datetime.now().isoformat()
        event_type = str(raw.get('type') or '').strip() or 'history_event'

        normalized.append(
            {
                'seq': seq_value,
                'task_id': str(raw.get('task_id') or task_id),
                'type': event_type,
                'round': round_number,
                'payload': payload,
                'created_at': created_at,
            }
        )
        next_seq = max(next_seq + 1, seq_value + 1)

    normalized.sort(key=lambda item: int(item.get('seq', 0)))
    return normalized


def read_json_file(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    try:
        raw = path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def guess_task_created_at(task_dir: Path | None, state: dict) -> str:
    if task_dir is None:
        return ''
    events_path = task_dir / 'events.jsonl'
    if events_path.exists():
        try:
            for raw in events_path.read_text(encoding='utf-8', errors='replace').splitlines():
                text = str(raw or '').strip()
                if not text:
                    continue
                try:
                    obj = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    created_at = str(obj.get('created_at') or '').strip()
                    if created_at:
                        return created_at
        except OSError:
            pass
    updated = str(state.get('updated_at') or '').strip()
    if updated:
        return updated
    return ''


def guess_task_updated_at(task_dir: Path | None) -> str:
    if task_dir is None:
        return ''
    events_path = task_dir / 'events.jsonl'
    if events_path.exists():
        try:
            lines = [line.strip() for line in events_path.read_text(encoding='utf-8', errors='replace').splitlines() if line.strip()]
        except OSError:
            lines = []
        for raw in reversed(lines):
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                created_at = str(obj.get('created_at') or '').strip()
                if created_at:
                    return created_at
    try:
        return datetime.fromtimestamp(task_dir.stat().st_mtime).isoformat()
    except OSError:
        return ''


def load_history_events(*, repository, task_id: str, row: dict, task_dir: Path | None, logger) -> list[dict]:
    if row:
        try:
            events = repository.list_events(task_id)
            if events:
                return events
        except Exception:
            logger.exception('list_events_failed task_id=%s', task_id)

    if task_dir is None:
        return []
    path = task_dir / 'events.jsonl'
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        for raw in path.read_text(encoding='utf-8', errors='replace').splitlines():
            text = str(raw or '').strip()
            if not text:
                continue
            try:
                obj = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                out.append(obj)
    except OSError:
        return []
    return out


def clip_snippet(value, *, max_chars: int = 220) -> str:
    text = str(value or '').strip()
    if not text:
        return ''
    one_line = text.replace('\r', ' ').replace('\n', ' ')
    if len(one_line) <= max_chars:
        return one_line
    return one_line[:max_chars].rstrip() + '...'


def read_markdown_highlights(path: Path | None) -> list[str]:
    if path is None or not path.exists():
        return []
    try:
        raw = path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return []
    lines: list[str] = []
    for item in raw.splitlines():
        text = str(item or '').strip()
        if not text:
            continue
        if text.startswith('#'):
            continue
        lines.append(text)
        if len(lines) >= 5:
            break
    return [clip_snippet(v) for v in lines if clip_snippet(v)]


def merged_event_payload(event: dict) -> dict:
    payload = event.get('payload') if isinstance(event.get('payload'), dict) else {}
    out = dict(payload) if isinstance(payload, dict) else {}
    for key in (
        'output',
        'reason',
        'verdict',
        'participant',
        'provider',
        'mode',
        'changed_files',
        'copied_files',
        'deleted_files',
        'snapshot_path',
        'changelog_path',
        'merged_at',
    ):
        if key not in out and key in event:
            out[key] = event.get(key)
    return out


def extract_core_findings(*, task_dir: Path | None, events: list[dict], fallback_reason: str | None) -> list[str]:
    findings: list[str] = []
    for line in read_markdown_highlights(task_dir / 'summary.md' if task_dir else None):
        if line not in findings:
            findings.append(line)
        if len(findings) >= 3:
            return findings

    for line in read_markdown_highlights(task_dir / 'final_report.md' if task_dir else None):
        if line not in findings:
            findings.append(line)
        if len(findings) >= 3:
            return findings

    interesting = {
        'gate_failed',
        'gate_passed',
        'manual_gate',
        'review',
        'proposal_review',
        'discussion',
        'debate_review',
        'debate_reply',
    }
    for event in events:
        etype = str(event.get('type') or '').strip().lower()
        if etype not in interesting:
            continue
        payload = merged_event_payload(event)
        snippet = (
            clip_snippet(payload.get('output'))
            or clip_snippet(payload.get('reason'))
            or clip_snippet(event.get('type'))
        )
        if not snippet:
            continue
        if snippet not in findings:
            findings.append(snippet)
        if len(findings) >= 3:
            return findings

    if fallback_reason and not findings:
        findings.append(f'Final reason: {fallback_reason}')

    return findings


def coerce_revision_count(value) -> int:
    if value is None:
        return 0
    if isinstance(value, (list, tuple, set, dict)):
        return len(value)
    if isinstance(value, bool):
        return int(value)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        pass
    text = str(value or '').strip()
    if not text:
        return 0
    try:
        return max(0, int(float(text)))
    except (TypeError, ValueError):
        return 0


def extract_revisions(*, task_dir: Path | None, events: list[dict]) -> dict:
    summary_path = (task_dir / 'artifacts' / 'auto_merge_summary.json') if task_dir is not None else None
    summary = read_json_file(summary_path) if summary_path else {}
    if not summary:
        for event in reversed(events):
            if str(event.get('type') or '').strip().lower() != EventType.AUTO_MERGE_COMPLETED.value:
                continue
            payload = merged_event_payload(event)
            if isinstance(payload, dict):
                summary = payload
                break

    if not summary:
        return {'auto_merge': False}

    return {
        'auto_merge': True,
        'mode': str(summary.get('mode') or '').strip() or None,
        'changed_files': coerce_revision_count(summary.get('changed_files')),
        'copied_files': coerce_revision_count(summary.get('copied_files')),
        'deleted_files': coerce_revision_count(summary.get('deleted_files')),
        'snapshot_path': str(summary.get('snapshot_path') or '').strip() or None,
        'changelog_path': str(summary.get('changelog_path') or '').strip() or None,
        'merged_at': str(summary.get('merged_at') or '').strip() or None,
    }


def extract_disputes(events: list[dict]) -> list[dict]:
    disputes: list[dict] = []
    for event in events:
        etype = str(event.get('type') or '').strip().lower()
        payload = merged_event_payload(event)

        if etype in {EventType.REVIEW.value, EventType.PROPOSAL_REVIEW.value}:
            verdict = str(payload.get('verdict') or '').strip().lower()
            if verdict not in {ReviewVerdict.BLOCKER.value, ReviewVerdict.UNKNOWN.value}:
                continue
            disputes.append(
                {
                    'participant': str(payload.get('participant') or 'reviewer'),
                    'verdict': verdict,
                    'note': clip_snippet(payload.get('output')) or 'review raised concerns',
                }
            )
        elif etype == EventType.GATE_FAILED.value:
            reason = str(payload.get('reason') or '').strip()
            if not reason:
                continue
            disputes.append(
                {
                    'participant': 'system',
                    'verdict': 'gate_failed',
                    'note': clip_snippet(reason) or reason,
                }
            )

        if len(disputes) >= 5:
            break

    return disputes


def derive_next_steps(*, status: str, reason: str | None, disputes: list[dict]) -> list[str]:
    s = str(status or '').strip().lower()
    r = str(reason or '').strip()
    if s == TaskStatus.WAITING_MANUAL.value:
        if r.startswith('proposal_consensus_stalled'):
            return ['Proposal discussion stalled. Use Custom Reply + Re-run to provide specific direction, then continue.']
        return ['Approve + Start to continue, or Reject to cancel this proposal.']
    if s == TaskStatus.RUNNING.value:
        return ['Task is still executing. Watch latest stage events or worker logs for progress.']
    if s == TaskStatus.QUEUED.value:
        return ['Start the task when ready, or keep it queued for scheduling.']
    if s == TaskStatus.PASSED.value:
        return ['Task passed. Optionally launch a follow-up evolution task for additional improvements.']
    if s == TaskStatus.FAILED_GATE.value:
        if disputes:
            return ['Address blocker/unknown review points, then rerun the task.']
        return [f'Address gate failure reason: {r}' if r else 'Address gate failures, then rerun.']
    if s == TaskStatus.FAILED_SYSTEM.value:
        return [f'Fix system issue: {r}' if r else 'Fix system/runtime issue, then rerun.']
    if s == TaskStatus.CANCELED.value:
        return ['Task was canceled. Recreate or restart only if requirements still apply.']
    return ['Inspect events and logs, then decide whether to rerun or revise scope.']
