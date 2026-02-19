from __future__ import annotations

from datetime import datetime
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
from typing import Callable
from uuid import uuid4

from awe_agentcheck.domain.models import TaskStatus
from awe_agentcheck.observability import get_logger
from awe_agentcheck.participants import get_supported_providers, parse_participant_id


_TERMINAL_STATUSES = {
    TaskStatus.PASSED.value,
    TaskStatus.FAILED_GATE.value,
    TaskStatus.FAILED_SYSTEM.value,
    TaskStatus.CANCELED.value,
}
_SUPPORTED_CONVERSATION_LANGUAGES = {'en', 'zh'}
_SUPPORTED_REPAIR_MODES = {'minimal', 'balanced', 'structural'}
_log = get_logger('awe_agentcheck.service_layers')


class AnalyticsService:
    def __init__(
        self,
        *,
        repository,
        stats_factory: Callable[..., object],
        reason_bucket_fn: Callable[[str | None], str | None],
        provider_pattern: re.Pattern,
        parse_iso_datetime_fn: Callable[[object], datetime | None],
        format_task_day_fn: Callable[[object], str],
        merged_event_payload_fn: Callable[[dict], dict],
    ):
        self.repository = repository
        self._stats_factory = stats_factory
        self._reason_bucket = reason_bucket_fn
        self._provider_pattern = provider_pattern
        self._parse_iso_datetime = parse_iso_datetime_fn
        self._format_task_day = format_task_day_fn
        self._merged_event_payload = merged_event_payload_fn

    def get_stats(self):
        rows = self.repository.list_tasks(limit=10_000)
        counts: dict[str, int] = {}
        reason_bucket_counts: dict[str, int] = {}
        provider_error_counts: dict[str, int] = {}
        for row in rows:
            status = str(row.get('status', 'unknown'))
            counts[status] = counts.get(status, 0) + 1

            reason = row.get('last_gate_reason')
            bucket = self._reason_bucket(reason)
            if bucket:
                reason_bucket_counts[bucket] = reason_bucket_counts.get(bucket, 0) + 1

            provider_match = self._provider_pattern.search(str(reason or ''))
            if provider_match:
                provider = provider_match.group(1).strip().lower()
                provider_error_counts[provider] = provider_error_counts.get(provider, 0) + 1

        active = counts.get(TaskStatus.RUNNING.value, 0) + counts.get(TaskStatus.QUEUED.value, 0)
        recent_rows = rows[:50]
        recent_terminal = [r for r in recent_rows if str(r.get('status', '')) in _TERMINAL_STATUSES]
        recent_terminal_total = len(recent_terminal)
        if recent_terminal_total > 0:
            pass_rate_50 = sum(1 for r in recent_terminal if str(r.get('status')) == TaskStatus.PASSED.value) / recent_terminal_total
            failed_gate_rate_50 = sum(1 for r in recent_terminal if str(r.get('status')) == TaskStatus.FAILED_GATE.value) / recent_terminal_total
            failed_system_rate_50 = sum(1 for r in recent_terminal if str(r.get('status')) == TaskStatus.FAILED_SYSTEM.value) / recent_terminal_total
        else:
            pass_rate_50 = 0.0
            failed_gate_rate_50 = 0.0
            failed_system_rate_50 = 0.0

        durations: list[float] = []
        for row in recent_terminal:
            created = self._parse_iso_datetime(row.get('created_at'))
            updated = self._parse_iso_datetime(row.get('updated_at'))
            if created is None or updated is None:
                continue
            delta = (updated - created).total_seconds()
            if delta >= 0:
                durations.append(delta)
        mean_task_duration_seconds_50 = (sum(durations) / len(durations)) if durations else 0.0

        return self._stats_factory(
            total_tasks=len(rows),
            status_counts=counts,
            active_tasks=active,
            reason_bucket_counts=reason_bucket_counts,
            provider_error_counts=provider_error_counts,
            recent_terminal_total=recent_terminal_total,
            pass_rate_50=pass_rate_50,
            failed_gate_rate_50=failed_gate_rate_50,
            failed_system_rate_50=failed_system_rate_50,
            mean_task_duration_seconds_50=mean_task_duration_seconds_50,
        )

    def get_analytics(self, *, limit: int = 300) -> dict:
        rows = self.repository.list_tasks(limit=max(1, min(2000, int(limit))))
        failures = [row for row in rows if str(row.get('status') or '') == TaskStatus.FAILED_GATE.value]
        total_failures = len(failures)

        failure_taxonomy: dict[str, int] = {}
        trend_by_day: dict[str, dict[str, int]] = {}
        for row in failures:
            reason = str(row.get('last_gate_reason') or '')
            bucket = self._reason_bucket(reason) or 'other'
            failure_taxonomy[bucket] = failure_taxonomy.get(bucket, 0) + 1

            day = self._format_task_day(row.get('updated_at') or row.get('created_at'))
            day_bucket = trend_by_day.setdefault(day, {})
            day_bucket[bucket] = day_bucket.get(bucket, 0) + 1

        taxonomy_rows: list[dict] = []
        for bucket, count in sorted(failure_taxonomy.items(), key=lambda item: (-item[1], item[0])):
            share = (count / total_failures) if total_failures else 0.0
            taxonomy_rows.append({'bucket': bucket, 'count': count, 'share': round(share, 4)})

        trend_rows: list[dict] = []
        for day in sorted(trend_by_day.keys()):
            day_counts = trend_by_day[day]
            trend_rows.append(
                {
                    'day': day,
                    'total': int(sum(day_counts.values())),
                    'buckets': dict(sorted(day_counts.items(), key=lambda item: (-item[1], item[0]))),
                }
            )

        reviewer_counts: dict[str, dict[str, int]] = {}
        global_counts = {'no_blocker': 0, 'blocker': 0, 'unknown': 0}
        for row in rows:
            task_id = str(row.get('task_id') or '').strip()
            if not task_id:
                continue
            try:
                events = self.repository.list_events(task_id)
            except Exception:
                events = []
            for event in events:
                etype = str(event.get('type') or '').strip().lower()
                if etype not in {'review', 'proposal_review', 'proposal_precheck_review', 'debate_review'}:
                    continue
                payload = self._merged_event_payload(event)
                participant = str(payload.get('participant') or '').strip()
                if not participant:
                    continue
                verdict = str(payload.get('verdict') or '').strip().lower()
                if verdict not in {'no_blocker', 'blocker', 'unknown'}:
                    verdict = 'unknown'

                bucket = reviewer_counts.setdefault(participant, {'no_blocker': 0, 'blocker': 0, 'unknown': 0})
                bucket[verdict] = int(bucket.get(verdict, 0)) + 1
                global_counts[verdict] = int(global_counts.get(verdict, 0)) + 1

        global_total = int(sum(global_counts.values()))
        global_adverse_rate = (
            (global_counts.get('blocker', 0) + global_counts.get('unknown', 0)) / global_total
            if global_total
            else 0.0
        )

        reviewer_rows: list[dict] = []
        for participant, counts in reviewer_counts.items():
            total = int(sum(int(v) for v in counts.values()))
            if total <= 0:
                continue
            blocker_rate = counts.get('blocker', 0) / total
            unknown_rate = counts.get('unknown', 0) / total
            no_blocker_rate = counts.get('no_blocker', 0) / total
            adverse_rate = blocker_rate + unknown_rate
            reviewer_rows.append(
                {
                    'participant': participant,
                    'reviews': total,
                    'no_blocker_rate': round(no_blocker_rate, 4),
                    'blocker_rate': round(blocker_rate, 4),
                    'unknown_rate': round(unknown_rate, 4),
                    'adverse_rate': round(adverse_rate, 4),
                    'drift_score': round(abs(adverse_rate - global_adverse_rate), 4),
                }
            )

        reviewer_rows.sort(key=lambda item: (-float(item.get('drift_score', 0.0)), -int(item.get('reviews', 0)), item.get('participant', '')))

        return {
            'generated_at': datetime.now().isoformat(),
            'window_tasks': len(rows),
            'window_failed_gate': total_failures,
            'failure_taxonomy': taxonomy_rows,
            'failure_taxonomy_trend': trend_rows,
            'reviewer_global': {
                'reviews': global_total,
                'no_blocker_rate': round((global_counts.get('no_blocker', 0) / global_total) if global_total else 0.0, 4),
                'blocker_rate': round((global_counts.get('blocker', 0) / global_total) if global_total else 0.0, 4),
                'unknown_rate': round((global_counts.get('unknown', 0) / global_total) if global_total else 0.0, 4),
                'adverse_rate': round(global_adverse_rate, 4),
            },
            'reviewer_drift': reviewer_rows,
        }


class HistoryService:
    def __init__(
        self,
        *,
        repository,
        artifact_store,
        normalize_project_path_key_fn: Callable[[object], str],
        build_project_history_item_fn: Callable[..., dict | None],
        read_git_state_fn: Callable[[Path | None], dict],
        collect_task_artifacts_fn: Callable[..., list[dict]],
        clip_snippet_fn: Callable[..., str],
    ):
        self.repository = repository
        self.artifact_store = artifact_store
        self._normalize_project_path_key = normalize_project_path_key_fn
        self._build_project_history_item = build_project_history_item_fn
        self._read_git_state = read_git_state_fn
        self._collect_task_artifacts = collect_task_artifacts_fn
        self._clip_snippet = clip_snippet_fn

    def build_github_pr_summary(self, task_id: str) -> dict:
        row = self.repository.get_task(task_id)
        if row is None:
            raise KeyError(task_id)

        project_path = str(row.get('project_path') or row.get('workspace_path') or '').strip()
        git = self._read_git_state(Path(project_path) if project_path else None)

        history_items = self.list_project_history(project_path=project_path, limit=500)
        history = next((item for item in history_items if str(item.get('task_id') or '') == task_id), None)

        findings = list(history.get('core_findings', [])) if isinstance(history, dict) else []
        revisions = dict(history.get('revisions', {})) if isinstance(history, dict) else {}
        disputes = list(history.get('disputes', [])) if isinstance(history, dict) else []
        next_steps = list(history.get('next_steps', [])) if isinstance(history, dict) else []

        artifacts = self._collect_task_artifacts(task_id=task_id)

        lines: list[str] = []
        lines.append(f'### AWE-AgentForge Task Summary | {task_id}')
        lines.append('')
        lines.append(f'- Title: {row.get("title")}')
        lines.append(f'- Status: {row.get("status")}')
        lines.append(f'- Last reason: {row.get("last_gate_reason") or "n/a"}')
        lines.append(f'- Rounds: {row.get("rounds_completed", 0)}/{row.get("max_rounds", 1)}')
        lines.append(f'- Project path: `{project_path}`')
        if git.get('is_git_repo'):
            lines.append(f'- Git branch: `{git.get("branch") or "detached"}`')
            lines.append(f'- Git worktree clean: `{git.get("worktree_clean")}`')
            if git.get('remote_origin'):
                lines.append(f'- Git remote: `{git.get("remote_origin")}`')
        lines.append('')
        lines.append('#### Core Findings')
        if findings:
            for item in findings[:5]:
                lines.append(f'- {item}')
        else:
            lines.append('- n/a')
        lines.append('')
        lines.append('#### Revisions')
        if revisions:
            lines.append(f'- auto_merge: `{bool(revisions.get("auto_merge", False))}`')
            lines.append(f'- mode: `{revisions.get("mode") or "n/a"}`')
            lines.append(f'- changed_files: `{int(revisions.get("changed_files") or 0)}`')
            lines.append(f'- copied_files: `{int(revisions.get("copied_files") or 0)}`')
            lines.append(f'- deleted_files: `{int(revisions.get("deleted_files") or 0)}`')
            if revisions.get('snapshot_path'):
                lines.append(f'- snapshot_path: `{revisions.get("snapshot_path")}`')
            if revisions.get('changelog_path'):
                lines.append(f'- changelog_path: `{revisions.get("changelog_path")}`')
        else:
            lines.append('- n/a')
        lines.append('')
        lines.append('#### Review Disputes')
        if disputes:
            for item in disputes[:5]:
                lines.append(
                    f'- {item.get("participant", "reviewer")} | {item.get("verdict", "unknown")}: '
                    f'{self._clip_snippet(item.get("note")) or "n/a"}'
                )
        else:
            lines.append('- none')
        lines.append('')
        lines.append('#### Next Steps')
        if next_steps:
            for item in next_steps[:5]:
                lines.append(f'- {item}')
        else:
            lines.append('- n/a')
        lines.append('')
        lines.append('#### Task Artifacts')
        if artifacts:
            for item in artifacts:
                lines.append(f'- {item["name"]}: `{item["path"]}`')
        else:
            lines.append('- n/a')

        return {
            'task_id': task_id,
            'project_path': project_path,
            'status': str(row.get('status') or ''),
            'git': git,
            'summary_markdown': '\n'.join(lines).strip() + '\n',
            'artifacts': artifacts,
        }

    def list_project_history(self, *, project_path: str | None = None, limit: int = 200) -> list[dict]:
        limit_int = max(1, min(1000, int(limit)))
        requested_project = self._normalize_project_path_key(project_path) if str(project_path or '').strip() else None

        rows = self.repository.list_tasks(limit=10_000)
        row_by_id: dict[str, dict] = {}
        for row in rows:
            task_id = str(row.get('task_id', '')).strip()
            if task_id:
                row_by_id[task_id] = row

        items: list[dict] = []
        seen: set[str] = set()
        threads_root = self.artifact_store.root / 'threads'
        thread_dirs: list[tuple[float, Path]] = []
        if threads_root.exists() and threads_root.is_dir():
            for child in threads_root.iterdir():
                if not child.is_dir():
                    continue
                try:
                    stamp = float(child.stat().st_mtime)
                except OSError:
                    stamp = 0.0
                thread_dirs.append((stamp, child))
            thread_dirs.sort(key=lambda pair: pair[0], reverse=True)

        for _, task_dir in thread_dirs:
            task_id = str(task_dir.name or '').strip()
            if not task_id:
                continue
            item = self._build_project_history_item(task_id=task_id, row=row_by_id.get(task_id), task_dir=task_dir)
            if item is None:
                continue
            project_key = self._normalize_project_path_key(item.get('project_path'))
            if requested_project and project_key != requested_project:
                continue
            items.append(item)
            seen.add(task_id)
            if len(items) >= limit_int:
                return items

        for row in rows:
            task_id = str(row.get('task_id', '')).strip()
            if not task_id or task_id in seen:
                continue
            item = self._build_project_history_item(task_id=task_id, row=row, task_dir=None)
            if item is None:
                continue
            project_key = self._normalize_project_path_key(item.get('project_path'))
            if requested_project and project_key != requested_project:
                continue
            items.append(item)
            if len(items) >= limit_int:
                break

        return items


class TaskManagementService:
    def __init__(
        self,
        *,
        repository,
        artifact_store,
        validation_error_cls,
    ):
        self.repository = repository
        self.artifact_store = artifact_store
        self._validation_error_cls = validation_error_cls

    def create_task(self, payload) -> dict:
        try:
            author_participant = parse_participant_id(payload.author_participant)
        except ValueError as exc:
            raise self._validation_error_cls(
                f'invalid author_participant: {exc}',
                field='author_participant',
            ) from exc

        reviewer_participants: list[str] = []
        for i, rp in enumerate(payload.reviewer_participants):
            try:
                reviewer_participants.append(parse_participant_id(rp).participant_id)
            except ValueError as exc:
                raise self._validation_error_cls(
                    f'invalid reviewer_participants[{i}]: {exc}',
                    field=f'reviewer_participants[{i}]',
                ) from exc

        project_root = Path(payload.workspace_path).resolve()
        if not project_root.exists() or not project_root.is_dir():
            raise self._validation_error_cls(
                'workspace_path must be an existing directory',
                field='workspace_path',
            )

        evolution_level = max(0, min(2, int(payload.evolution_level)))
        evolve_until = self._normalize_evolve_until(payload.evolve_until)
        conversation_language = self._normalize_conversation_language(
            payload.conversation_language,
            strict=True,
        )
        provider_models = self._normalize_provider_models(payload.provider_models)
        provider_model_params = self._normalize_provider_model_params(payload.provider_model_params)
        known_participants = {author_participant.participant_id, *reviewer_participants}
        participant_models = self._normalize_participant_models(
            payload.participant_models,
            known_participants=known_participants,
        )
        participant_model_params = self._normalize_participant_model_params(
            payload.participant_model_params,
            known_participants=known_participants,
        )
        claude_team_agents = bool(payload.claude_team_agents)
        codex_multi_agents = bool(payload.codex_multi_agents)
        claude_team_agents_overrides = self._normalize_participant_agent_overrides(
            payload.claude_team_agents_overrides,
            known_participants=known_participants,
            required_provider='claude',
            field='claude_team_agents_overrides',
        )
        codex_multi_agents_overrides = self._normalize_participant_agent_overrides(
            payload.codex_multi_agents_overrides,
            known_participants=known_participants,
            required_provider='codex',
            field='codex_multi_agents_overrides',
        )
        repair_mode = self._normalize_repair_mode(payload.repair_mode, strict=True)
        plain_mode = self._normalize_plain_mode(payload.plain_mode)
        stream_mode = self._normalize_bool_flag(payload.stream_mode, default=True)
        debate_mode = self._normalize_bool_flag(payload.debate_mode, default=True)
        sandbox_mode = bool(payload.sandbox_mode)
        self_loop_mode = max(0, min(1, int(payload.self_loop_mode)))
        sandbox_cleanup_on_pass = bool(payload.sandbox_cleanup_on_pass)
        sandbox_workspace_path = self._normalize_merge_target_path(payload.sandbox_workspace_path)
        sandbox_generated = False
        auto_merge = bool(payload.auto_merge)
        max_rounds = max(1, min(20, int(payload.max_rounds)))
        multi_round_manual_promote = max_rounds > 1 and not auto_merge
        if multi_round_manual_promote:
            sandbox_mode = True
            sandbox_workspace_path = None
        merge_target_path = self._normalize_merge_target_path(payload.merge_target_path)
        if auto_merge and sandbox_mode and not merge_target_path:
            merge_target_path = str(project_root)
        if auto_merge and merge_target_path:
            merge_target = Path(merge_target_path)
            if not merge_target.exists() or not merge_target.is_dir():
                raise self._validation_error_cls(
                    'merge_target_path must be an existing directory',
                    field='merge_target_path',
                )

        workspace_root = project_root
        sandbox_root: Path | None = None
        workspace_fingerprint: dict[str, object] = {}
        try:
            if sandbox_mode:
                if not sandbox_workspace_path:
                    sandbox_workspace_path = self._default_sandbox_path(project_root)
                    sandbox_generated = True
                sandbox_root = Path(sandbox_workspace_path)
                if sandbox_root.exists() and not sandbox_root.is_dir():
                    raise self._validation_error_cls(
                        'sandbox_workspace_path must be a directory',
                        field='sandbox_workspace_path',
                    )
                sandbox_root.mkdir(parents=True, exist_ok=True)
                self._bootstrap_sandbox_workspace(project_root, sandbox_root)
                workspace_root = sandbox_root
            else:
                sandbox_workspace_path = None
                sandbox_generated = False

            workspace_fingerprint = self._build_workspace_fingerprint(
                project_root=project_root,
                workspace_root=Path(workspace_root),
                sandbox_mode=sandbox_mode,
                sandbox_workspace_path=sandbox_workspace_path,
                merge_target_path=merge_target_path,
            )

            row = self.repository.create_task(
                title=payload.title,
                description=payload.description,
                author_participant=author_participant.participant_id,
                reviewer_participants=reviewer_participants,
                evolution_level=evolution_level,
                evolve_until=evolve_until,
                conversation_language=conversation_language,
                provider_models=provider_models,
                provider_model_params=provider_model_params,
                participant_models=participant_models,
                participant_model_params=participant_model_params,
                claude_team_agents=claude_team_agents,
                codex_multi_agents=codex_multi_agents,
                claude_team_agents_overrides=claude_team_agents_overrides,
                codex_multi_agents_overrides=codex_multi_agents_overrides,
                repair_mode=repair_mode,
                plain_mode=plain_mode,
                stream_mode=stream_mode,
                debate_mode=debate_mode,
                sandbox_mode=sandbox_mode,
                sandbox_workspace_path=sandbox_workspace_path,
                sandbox_generated=sandbox_generated,
                sandbox_cleanup_on_pass=sandbox_cleanup_on_pass,
                project_path=str(project_root),
                self_loop_mode=self_loop_mode,
                auto_merge=auto_merge,
                merge_target_path=merge_target_path,
                workspace_path=str(workspace_root),
                workspace_fingerprint=workspace_fingerprint,
                max_rounds=max_rounds,
                test_command=payload.test_command,
                lint_command=payload.lint_command,
            )
            self.artifact_store.create_task_workspace(row['task_id'])
            self.artifact_store.update_state(
                row['task_id'],
                {
                    'status': row['status'],
                    'rounds_completed': row.get('rounds_completed', 0),
                    'cancel_requested': row.get('cancel_requested', False),
                    'conversation_language': str(row.get('conversation_language') or 'en'),
                    'provider_models': dict(row.get('provider_models', {})),
                    'provider_model_params': dict(row.get('provider_model_params', {})),
                    'participant_models': dict(row.get('participant_models', {})),
                    'participant_model_params': dict(row.get('participant_model_params', {})),
                    'claude_team_agents': bool(row.get('claude_team_agents', False)),
                    'codex_multi_agents': bool(row.get('codex_multi_agents', False)),
                    'claude_team_agents_overrides': dict(row.get('claude_team_agents_overrides', {})),
                    'codex_multi_agents_overrides': dict(row.get('codex_multi_agents_overrides', {})),
                    'repair_mode': str(row.get('repair_mode') or 'balanced'),
                    'plain_mode': bool(row.get('plain_mode', True)),
                    'stream_mode': bool(row.get('stream_mode', True)),
                    'debate_mode': bool(row.get('debate_mode', True)),
                    'sandbox_mode': bool(row.get('sandbox_mode', False)),
                    'sandbox_workspace_path': row.get('sandbox_workspace_path'),
                    'sandbox_generated': bool(row.get('sandbox_generated', False)),
                    'sandbox_cleanup_on_pass': bool(row.get('sandbox_cleanup_on_pass', False)),
                    'self_loop_mode': int(row.get('self_loop_mode', 0)),
                    'project_path': row.get('project_path'),
                    'auto_merge': bool(row.get('auto_merge', True)),
                    'merge_target_path': row.get('merge_target_path'),
                    'workspace_fingerprint': dict(row.get('workspace_fingerprint', workspace_fingerprint)),
                },
            )
        except Exception:
            self._cleanup_create_task_sandbox_failure(
                sandbox_mode=sandbox_mode,
                sandbox_generated=sandbox_generated,
                project_root=project_root,
                sandbox_root=sandbox_root,
            )
            raise

        _log.info('task_created task_id=%s title=%s', row['task_id'], payload.title)
        return row

    def list_tasks(self, *, limit: int = 100) -> list[dict]:
        return self.repository.list_tasks(limit=limit)

    def get_task(self, task_id: str) -> dict | None:
        return self.repository.get_task(task_id)

    @staticmethod
    def _supported_providers() -> set[str]:
        return get_supported_providers()

    def _normalize_evolve_until(self, value: str | None) -> str | None:
        text = str(value or '').strip()
        if not text:
            return None
        candidate = text.replace(' ', 'T')
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError as exc:
            raise self._validation_error_cls(
                'evolve_until must be ISO/local datetime',
                field='evolve_until',
            ) from exc
        return parsed.replace(microsecond=0).isoformat()

    @staticmethod
    def _normalize_merge_target_path(value: str | None) -> str | None:
        text = str(value or '').strip()
        if not text:
            return None
        return str(Path(text))

    def _normalize_conversation_language(self, value: str | None, *, strict: bool = False) -> str:
        text = str(value or '').strip().lower()
        if not text:
            return 'en'
        aliases = {
            'en': 'en',
            'english': 'en',
            'eng': 'en',
            'zh': 'zh',
            'zh-cn': 'zh',
            'cn': 'zh',
            'chinese': 'zh',
            '中文': 'zh',
        }
        normalized = aliases.get(text, text)
        if normalized not in _SUPPORTED_CONVERSATION_LANGUAGES:
            if strict:
                raise self._validation_error_cls(
                    f'invalid conversation_language: {text}',
                    field='conversation_language',
                )
            return 'en'
        return normalized

    def _normalize_repair_mode(self, value, *, strict: bool = False) -> str:
        text = str(value or '').strip().lower()
        if not text:
            return 'balanced'
        if text not in _SUPPORTED_REPAIR_MODES:
            if strict:
                raise self._validation_error_cls(
                    f'invalid repair_mode: {text}',
                    field='repair_mode',
                )
            return 'balanced'
        return text

    @staticmethod
    def _normalize_plain_mode(value) -> bool:
        text = str(value).strip().lower()
        if text in {'0', 'false', 'no', 'off'}:
            return False
        if text in {'1', 'true', 'yes', 'on'}:
            return True
        return bool(value)

    @staticmethod
    def _normalize_bool_flag(value, *, default: bool) -> bool:
        text = str(value).strip().lower()
        if text in {'0', 'false', 'no', 'off'}:
            return False
        if text in {'1', 'true', 'yes', 'on'}:
            return True
        if text in {'', 'none'}:
            return bool(default)
        return bool(value)

    def _normalize_provider_models(self, value: dict[str, str] | None) -> dict[str, str]:
        if not value:
            return {}
        if not isinstance(value, dict):
            raise self._validation_error_cls('provider_models must be an object', field='provider_models')

        out: dict[str, str] = {}
        supported = self._supported_providers()
        for raw_provider, raw_model in value.items():
            provider = str(raw_provider or '').strip().lower()
            model = str(raw_model or '').strip()
            if provider not in supported:
                raise self._validation_error_cls(
                    f'invalid provider_models key: {provider}',
                    field='provider_models',
                )
            if not model:
                raise self._validation_error_cls(
                    f'provider_models[{provider}] cannot be empty',
                    field=f'provider_models[{provider}]',
                )
            out[provider] = model
        return out

    def _normalize_provider_model_params(self, value: dict[str, str] | None) -> dict[str, str]:
        if not value:
            return {}
        if not isinstance(value, dict):
            raise self._validation_error_cls('provider_model_params must be an object', field='provider_model_params')

        out: dict[str, str] = {}
        supported = self._supported_providers()
        for raw_provider, raw_params in value.items():
            provider = str(raw_provider or '').strip().lower()
            params = str(raw_params or '').strip()
            if provider not in supported:
                raise self._validation_error_cls(
                    f'invalid provider_model_params key: {provider}',
                    field='provider_model_params',
                )
            if not params:
                raise self._validation_error_cls(
                    f'provider_model_params[{provider}] cannot be empty',
                    field=f'provider_model_params[{provider}]',
                )
            out[provider] = params
        return out

    def _normalize_participant_models(
        self,
        value: dict[str, str] | None,
        *,
        known_participants: set[str],
    ) -> dict[str, str]:
        if not value:
            return {}
        if not isinstance(value, dict):
            raise self._validation_error_cls('participant_models must be an object', field='participant_models')

        known = {str(v or '').strip() for v in known_participants if str(v or '').strip()}
        known_lower = {v.lower() for v in known}
        out: dict[str, str] = {}
        for raw_participant, raw_model in value.items():
            participant = str(raw_participant or '').strip()
            model = str(raw_model or '').strip()
            if not participant:
                raise self._validation_error_cls(
                    'participant_models key cannot be empty',
                    field='participant_models',
                )
            if participant.lower() not in known_lower:
                raise self._validation_error_cls(
                    f'participant_models key is not in task participants: {participant}',
                    field='participant_models',
                )
            if not model:
                raise self._validation_error_cls(
                    f'participant_models[{participant}] cannot be empty',
                    field=f'participant_models[{participant}]',
                )
            out[participant] = model
        return out

    def _normalize_participant_model_params(
        self,
        value: dict[str, str] | None,
        *,
        known_participants: set[str],
    ) -> dict[str, str]:
        if not value:
            return {}
        if not isinstance(value, dict):
            raise self._validation_error_cls(
                'participant_model_params must be an object',
                field='participant_model_params',
            )

        known = {str(v or '').strip() for v in known_participants if str(v or '').strip()}
        known_lower = {v.lower() for v in known}
        out: dict[str, str] = {}
        for raw_participant, raw_params in value.items():
            participant = str(raw_participant or '').strip()
            params = str(raw_params or '').strip()
            if not participant:
                raise self._validation_error_cls(
                    'participant_model_params key cannot be empty',
                    field='participant_model_params',
                )
            if participant.lower() not in known_lower:
                raise self._validation_error_cls(
                    f'participant_model_params key is not in task participants: {participant}',
                    field='participant_model_params',
                )
            if not params:
                raise self._validation_error_cls(
                    f'participant_model_params[{participant}] cannot be empty',
                    field=f'participant_model_params[{participant}]',
                )
            out[participant] = params
        return out

    def _normalize_participant_agent_overrides(
        self,
        value: dict[str, bool] | None,
        *,
        known_participants: set[str],
        required_provider: str,
        field: str,
    ) -> dict[str, bool]:
        if not value:
            return {}
        if not isinstance(value, dict):
            raise self._validation_error_cls(f'{field} must be an object', field=field)

        known = {str(v or '').strip() for v in known_participants if str(v or '').strip()}
        known_map = {v.lower(): v for v in known}
        provider_required = str(required_provider or '').strip().lower()
        out: dict[str, bool] = {}
        for raw_participant, raw_enabled in value.items():
            participant = str(raw_participant or '').strip()
            if not participant:
                raise self._validation_error_cls(
                    f'{field} key cannot be empty',
                    field=field,
                )
            canonical = known_map.get(participant.lower())
            if not canonical:
                raise self._validation_error_cls(
                    f'{field} key is not in task participants: {participant}',
                    field=field,
                )
            provider = str(canonical.split('#', 1)[0] if '#' in canonical else '').strip().lower()
            if provider != provider_required:
                raise self._validation_error_cls(
                    f'{field}[{canonical}] must target provider={provider_required}',
                    field=f'{field}[{canonical}]',
                )
            enabled = self._coerce_bool_override_value(
                raw_enabled,
                field=f'{field}[{canonical}]',
            )
            out[canonical] = enabled
        return out

    def _coerce_bool_override_value(self, value, *, field: str) -> bool:
        if isinstance(value, bool):
            return value
        text = str(value or '').strip().lower()
        if text in {'1', 'true', 'yes', 'on'}:
            return True
        if text in {'0', 'false', 'no', 'off'}:
            return False
        raise self._validation_error_cls(
            f'{field} must be boolean',
            field=field,
        )

    @staticmethod
    def _normalize_fingerprint_path(path_text: str | None) -> str:
        text = str(path_text or '').strip()
        if not text:
            return ''
        try:
            resolved = Path(text).resolve(strict=False)
        except Exception:
            resolved = Path(text)
        normalized = str(resolved).replace('\\', '/')
        if os.name == 'nt':
            normalized = normalized.lower()
        return normalized

    @staticmethod
    def _workspace_head_signature(root: Path, *, max_entries: int = 128) -> str:
        target = Path(root)
        if not target.exists() or not target.is_dir():
            return 'missing'
        parts: list[str] = []
        try:
            children = sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        except OSError:
            return 'unreadable'
        for child in children:
            name = str(child.name or '').strip()
            if not name:
                continue
            if TaskManagementService._is_sandbox_ignored(name):
                continue
            kind = 'd' if child.is_dir() else 'f'
            label = name.lower() if os.name == 'nt' else name
            parts.append(f'{kind}:{label}')
            if len(parts) >= max_entries:
                break
        payload = '\n'.join(parts)
        if not payload:
            return 'empty'
        return hashlib.sha1(payload.encode('utf-8')).hexdigest()[:20]

    def _build_workspace_fingerprint(
        self,
        *,
        project_root: Path,
        workspace_root: Path,
        sandbox_mode: bool,
        sandbox_workspace_path: str | None,
        merge_target_path: str | None,
    ) -> dict[str, object]:
        project_resolved = Path(project_root).resolve(strict=False)
        workspace_resolved = Path(workspace_root).resolve(strict=False)
        return {
            'schema': 'workspace_fingerprint.v1',
            'project_path': self._normalize_fingerprint_path(str(project_resolved)),
            'workspace_path': self._normalize_fingerprint_path(str(workspace_resolved)),
            'sandbox_mode': bool(sandbox_mode),
            'sandbox_workspace_path': self._normalize_fingerprint_path(sandbox_workspace_path),
            'merge_target_path': self._normalize_fingerprint_path(merge_target_path),
            'project_has_git': bool((project_resolved / '.git').exists()),
            'workspace_head_signature': self._workspace_head_signature(workspace_resolved),
            'project_head_signature': self._workspace_head_signature(project_resolved),
        }

    @staticmethod
    def _default_sandbox_path(project_root: Path) -> str:
        configured_base = str(os.getenv('AWE_SANDBOX_BASE', '') or '').strip()
        if configured_base:
            base = Path(configured_base).resolve()
        else:
            shared_opt_in = str(os.getenv('AWE_SANDBOX_USE_PUBLIC_BASE', '') or '').strip().lower()
            if shared_opt_in in {'1', 'true', 'yes', 'on'}:
                if os.name == 'nt':
                    public_home = str(os.getenv('PUBLIC', 'C:/Users/Public') or 'C:/Users/Public').strip()
                    base = Path(public_home).resolve() / 'awe-agentcheck-sandboxes'
                else:
                    base = Path('/tmp/awe-agentcheck-sandboxes').resolve()
            else:
                base = Path.home().resolve() / '.awe-agentcheck' / 'sandboxes'
        root = base / f'{project_root.name}-lab'
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        suffix = uuid4().hex[:6]
        return str(root / f'{stamp}-{suffix}')

    @staticmethod
    def _cleanup_create_task_sandbox_failure(
        *,
        sandbox_mode: bool,
        sandbox_generated: bool,
        project_root: Path,
        sandbox_root: Path | None,
    ) -> None:
        if not sandbox_mode:
            return
        if not sandbox_generated:
            return
        if sandbox_root is None:
            return
        try:
            project_resolved = project_root.resolve()
            sandbox_resolved = sandbox_root.resolve()
        except Exception:
            return
        if sandbox_resolved == project_resolved:
            return
        try:
            if sandbox_resolved.exists():
                def _onerror(func, p, exc_info):
                    try:
                        os.chmod(p, stat.S_IWRITE)
                        func(p)
                    except Exception:
                        pass
                shutil.rmtree(sandbox_resolved, onerror=_onerror)
        except Exception:
            pass

    @staticmethod
    def _is_sandbox_ignored(rel_path: str) -> bool:
        normalized = rel_path.replace('\\', '/').strip()
        while normalized.startswith('./'):
            normalized = normalized[2:]
        while normalized.startswith('/'):
            normalized = normalized[1:]
        if not normalized:
            return False
        head = normalized.split('/', 1)[0]
        ignored_heads = {
            '.git',
            '.agents',
            '.claude',
            '.venv',
            '__pycache__',
            '.pytest_cache',
            '.ruff_cache',
            'node_modules',
            '.mypy_cache',
            '.idea',
            '.vscode',
        }
        if head in ignored_heads:
            return True
        if normalized.endswith('.pyc') or normalized.endswith('.pyo'):
            return True
        leaf = Path(normalized).name
        if TaskManagementService._is_windows_reserved_device_name(leaf):
            return True
        leaf = leaf.lower()
        if leaf == '.env' or leaf.startswith('.env.'):
            return True
        if leaf.endswith('.pem') or leaf.endswith('.key'):
            return True
        if re.search(r'(^|[._-])(token|tokens|secret|secrets|apikey|api-key|access-key)([._-]|$)', leaf):
            return True
        return False

    @staticmethod
    def _is_windows_reserved_device_name(filename: str) -> bool:
        normalized = str(filename or '').strip().rstrip(' .').lower()
        if not normalized:
            return False
        normalized = normalized.split(':', 1)[0]
        stem = normalized.split('.', 1)[0]
        if stem in {'con', 'prn', 'aux', 'nul'}:
            return True
        return bool(re.fullmatch(r'(com|lpt)[1-9]', stem))

    @staticmethod
    def _bootstrap_sandbox_workspace(project_root: Path, sandbox_root: Path) -> None:
        try:
            entries = list(sandbox_root.iterdir())
        except OSError:
            entries = []
        if entries:
            return

        for root, dirs, files in os.walk(project_root):
            root_path = Path(root)
            rel_root = root_path.relative_to(project_root)
            rel_root_text = '' if str(rel_root) == '.' else rel_root.as_posix()
            if rel_root_text and TaskManagementService._is_sandbox_ignored(rel_root_text):
                dirs[:] = []
                continue

            keep_dirs: list[str] = []
            for name in dirs:
                rel = f'{rel_root_text}/{name}' if rel_root_text else name
                if not TaskManagementService._is_sandbox_ignored(rel):
                    keep_dirs.append(name)
            dirs[:] = keep_dirs

            for filename in files:
                rel = f'{rel_root_text}/{filename}' if rel_root_text else filename
                if TaskManagementService._is_sandbox_ignored(rel):
                    continue
                src = root_path / filename
                dst = sandbox_root / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
