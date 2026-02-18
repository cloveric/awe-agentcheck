from __future__ import annotations

from dataclasses import dataclass

BUILTIN_PROVIDERS = frozenset({'claude', 'codex', 'gemini'})
# Backward-compatible alias used by existing callers/tests.
SUPPORTED_PROVIDERS = set(BUILTIN_PROVIDERS)
_EXTRA_PROVIDERS: set[str] = set()


def _normalize_provider_name(value: str) -> str:
    return str(value or '').strip().lower()


def set_extra_providers(providers: set[str] | list[str] | tuple[str, ...] | None) -> None:
    global _EXTRA_PROVIDERS
    incoming = providers or []
    cleaned: set[str] = set()
    for raw in incoming:
        provider = _normalize_provider_name(str(raw or ''))
        if not provider:
            continue
        if '#' in provider:
            continue
        cleaned.add(provider)
    _EXTRA_PROVIDERS = cleaned.difference(BUILTIN_PROVIDERS)


def register_provider(provider: str) -> None:
    name = _normalize_provider_name(provider)
    if not name:
        raise ValueError('provider cannot be empty')
    if '#' in name:
        raise ValueError('provider cannot contain #')
    if name in BUILTIN_PROVIDERS:
        return
    _EXTRA_PROVIDERS.add(name)


def get_supported_providers() -> set[str]:
    return set(BUILTIN_PROVIDERS).union(_EXTRA_PROVIDERS)


@dataclass(frozen=True)
class Participant:
    participant_id: str
    provider: str
    alias: str


def parse_participant_id(value: str) -> Participant:
    raw = (value or '').strip()
    if '#' not in raw:
        raise ValueError('participant id must be in provider#alias format')
    provider, alias = raw.split('#', 1)
    provider = provider.strip().lower()
    alias = alias.strip()
    if provider not in get_supported_providers():
        raise ValueError(f'unsupported provider: {provider}')
    if not alias:
        raise ValueError('participant alias cannot be empty')
    return Participant(participant_id=raw, provider=provider, alias=alias)
