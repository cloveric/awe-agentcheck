from __future__ import annotations

from dataclasses import dataclass
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path

from awe_agentcheck.participants import Participant

_VERDICT_RE = re.compile(r'^\s*VERDICT\s*:\s*(NO_BLOCKER|BLOCKER|UNKNOWN)\s*$', re.IGNORECASE)
_NEXT_RE = re.compile(r'^\s*NEXT_ACTION\s*:\s*(retry|pass|stop)\s*$', re.IGNORECASE)
_LIMIT_PATTERNS = (
    'hit your limit',
    'usage limit',
    'rate limit',
    'ratelimitexceeded',
    'resource_exhausted',
    'model_capacity_exhausted',
    'no capacity available',
    'quota exceeded',
    'insufficient_quota',
)
_MODEL_FLAG_BY_PROVIDER = {
    'claude': '--model',
    'codex': '-m',
    'gemini': '-m',
}


@dataclass(frozen=True)
class AdapterResult:
    output: str
    verdict: str
    next_action: str | None
    returncode: int
    duration_seconds: float


DEFAULT_COMMANDS = {
    'claude': 'claude -p --dangerously-skip-permissions --effort low --model claude-opus-4-6',
    'codex': 'codex exec --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox -c model_reasoning_effort=xhigh',
    'gemini': 'gemini --yolo',
}


def parse_verdict(output: str) -> str:
    for line in (output or '').splitlines():
        m = _VERDICT_RE.match(line)
        if m:
            return m.group(1).lower().replace('no_blocker', 'no_blocker')
    return 'unknown'


def parse_next_action(output: str) -> str | None:
    for line in (output or '').splitlines():
        m = _NEXT_RE.match(line)
        if m:
            return m.group(1).lower()
    return None


class ParticipantRunner:
    def __init__(
        self,
        *,
        command_overrides: dict[str, str] | None = None,
        dry_run: bool = False,
        timeout_retries: int = 1,
    ):
        self.commands = dict(DEFAULT_COMMANDS)
        if command_overrides:
            self.commands.update(command_overrides)
        self.dry_run = dry_run
        self.timeout_retries = max(0, int(timeout_retries))

    def run(
        self,
        *,
        participant: Participant,
        prompt: str,
        cwd: Path,
        timeout_seconds: int = 900,
        model: str | None = None,
        model_params: str | None = None,
        claude_team_agents: bool = False,
    ) -> AdapterResult:
        if self.dry_run:
            simulated = (
                f'[dry-run participant={participant.participant_id}]\\n'
                'VERDICT: NO_BLOCKER\\n'
                'NEXT_ACTION: pass\\n'
                'Simulated output for orchestration smoke testing.'
            )
            return AdapterResult(
                output=simulated,
                verdict='no_blocker',
                next_action='pass',
                returncode=0,
                duration_seconds=0.01,
            )

        command = self.commands.get(participant.provider)
        if not command:
            raise ValueError(f'no command configured for provider: {participant.provider}')

        argv = self._build_argv(
            command=command,
            provider=participant.provider,
            model=model,
            model_params=model_params,
            claude_team_agents=claude_team_agents,
        )
        argv = self._resolve_executable(argv)
        effective_command = self._format_command(argv)
        attempts = self.timeout_retries + 1
        current_prompt = prompt
        started = time.monotonic()
        completed = None
        for attempt in range(1, attempts + 1):
            runtime_argv, runtime_input = self._prepare_runtime_invocation(
                argv=argv,
                provider=participant.provider,
                prompt=current_prompt,
            )
            try:
                completed = subprocess.run(
                    runtime_argv,
                    input=runtime_input,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    cwd=str(cwd),
                    timeout=timeout_seconds,
                )
                break
            except FileNotFoundError as exc:
                raise RuntimeError(
                    f'command_not_found provider={participant.provider} command={effective_command}'
                ) from exc
            except subprocess.TimeoutExpired as exc:
                if attempt >= attempts:
                    raise RuntimeError(
                        f'command_timeout provider={participant.provider} command={effective_command} '
                        f'timeout_seconds={timeout_seconds} attempts={attempts}'
                    ) from exc
                current_prompt = self._clip_prompt_for_retry(current_prompt)
        assert completed is not None
        elapsed = time.monotonic() - started

        output = (completed.stdout or '').strip()
        if completed.returncode != 0:
            stderr = (completed.stderr or '').strip()
            output = '\n'.join([p for p in [output, stderr] if p]).strip()

        if self._is_provider_limit_output(output):
            raise RuntimeError(f'provider_limit provider={participant.provider} command={effective_command}')

        return AdapterResult(
            output=output,
            verdict=parse_verdict(output),
            next_action=parse_next_action(output),
            returncode=completed.returncode,
            duration_seconds=elapsed,
        )

    @staticmethod
    def _clip_prompt_for_retry(prompt: str) -> str:
        text = prompt or ''
        if len(text) <= 1200:
            return text
        kept = text[:1200]
        dropped = len(text) - len(kept)
        return kept + f'\n\n[retry prompt clipped: {dropped} chars removed]'

    @staticmethod
    def _is_provider_limit_output(output: str) -> bool:
        text = (output or '').strip().lower()
        if not text:
            return False
        return any(pattern in text for pattern in _LIMIT_PATTERNS)

    @staticmethod
    def _build_argv(
        *,
        command: str,
        provider: str,
        model: str | None,
        model_params: str | None,
        claude_team_agents: bool,
    ) -> list[str]:
        argv = shlex.split(command, posix=False)

        model_text = str(model or '').strip()
        if model_text and not ParticipantRunner._has_model_flag(argv):
            flag = _MODEL_FLAG_BY_PROVIDER.get(str(provider or '').strip().lower())
            if flag:
                argv.extend([flag, model_text])

        extra = ParticipantRunner._split_extra_args(model_params)
        if extra:
            argv.extend(extra)

        provider_text = str(provider or '').strip().lower()
        if provider_text == 'gemini':
            argv = ParticipantRunner._normalize_gemini_approval_flags(argv)

        if provider_text == 'claude':
            if claude_team_agents and not ParticipantRunner._has_agents_flag(argv):
                argv.extend(['--agents', '{}'])

        return argv

    @staticmethod
    def _prepare_runtime_invocation(*, argv: list[str], provider: str, prompt: str) -> tuple[list[str], str]:
        provider_text = str(provider or '').strip().lower()
        runtime_argv = list(argv)
        runtime_input = prompt
        if provider_text != 'gemini':
            return runtime_argv, runtime_input
        if ParticipantRunner._has_prompt_flag(runtime_argv):
            return runtime_argv, runtime_input
        # Gemini CLI is significantly more stable in non-interactive mode.
        runtime_argv.extend(['--prompt', prompt])
        runtime_input = ''
        return runtime_argv, runtime_input

    @staticmethod
    def _split_extra_args(value: str | None) -> list[str]:
        text = str(value or '').strip()
        if not text:
            return []
        try:
            return [str(v) for v in shlex.split(text, posix=False) if str(v).strip()]
        except ValueError:
            return [v for v in text.split() if v]

    @staticmethod
    def _has_model_flag(argv: list[str]) -> bool:
        for token in argv:
            text = str(token).strip()
            if text in {'--model', '-m'}:
                return True
            if text.startswith('--model='):
                return True
        return False

    @staticmethod
    def _has_agents_flag(argv: list[str]) -> bool:
        for token in argv:
            text = str(token).strip()
            if text == '--agents' or text.startswith('--agents='):
                return True
        return False

    @staticmethod
    def _has_prompt_flag(argv: list[str]) -> bool:
        for token in argv:
            text = str(token).strip()
            if text in {'-p', '--prompt'}:
                return True
            if text.startswith('--prompt='):
                return True
        return False

    @staticmethod
    def _normalize_gemini_approval_flags(argv: list[str]) -> list[str]:
        has_yolo = False
        has_approval_mode = False
        for token in argv:
            text = str(token).strip()
            if text in {'-y', '--yolo'}:
                has_yolo = True
            elif text == '--approval-mode' or text.startswith('--approval-mode='):
                has_approval_mode = True
        if not (has_yolo and has_approval_mode):
            return argv

        # Gemini CLI treats --yolo and --approval-mode as mutually exclusive.
        out: list[str] = []
        for token in argv:
            text = str(token).strip()
            if text in {'-y', '--yolo'}:
                continue
            out.append(str(token))
        return out

    @staticmethod
    def _resolve_executable(argv: list[str]) -> list[str]:
        if not argv:
            return argv
        first = str(argv[0]).strip()
        if not first:
            return argv
        resolved = shutil.which(first)
        if not resolved:
            return argv
        patched = list(argv)
        patched[0] = resolved
        return patched

    @staticmethod
    def _format_command(argv: list[str]) -> str:
        return ' '.join(str(v) for v in argv)
