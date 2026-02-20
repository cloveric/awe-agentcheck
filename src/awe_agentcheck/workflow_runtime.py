from __future__ import annotations

from awe_agentcheck.participants import Participant


def normalize_provider_models(value: dict[str, str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, raw in (value or {}).items():
        provider = str(key or '').strip().lower()
        model = str(raw or '').strip()
        if not provider or not model:
            continue
        out[provider] = model
    return out


def normalize_provider_model_params(value: dict[str, str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, raw in (value or {}).items():
        provider = str(key or '').strip().lower()
        params = str(raw or '').strip()
        if not provider or not params:
            continue
        out[provider] = params
    return out


def normalize_participant_models(value: dict[str, str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, raw in (value or {}).items():
        participant = str(key or '').strip()
        model = str(raw or '').strip()
        if not participant or not model:
            continue
        out[participant] = model
        out.setdefault(participant.lower(), model)
    return out


def normalize_participant_model_params(value: dict[str, str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, raw in (value or {}).items():
        participant = str(key or '').strip()
        params = str(raw or '').strip()
        if not participant or not params:
            continue
        out[participant] = params
        out.setdefault(participant.lower(), params)
    return out


def normalize_participant_agent_overrides(value: dict[str, bool] | None) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for key, raw in (value or {}).items():
        participant = str(key or '').strip()
        if not participant:
            continue
        if isinstance(raw, bool):
            enabled = raw
        else:
            text = str(raw or '').strip().lower()
            enabled = text in {'1', 'true', 'yes', 'on'}
        out[participant] = enabled
        out[participant.lower()] = enabled
    return out


def resolve_agent_toggle_for_participant(
    *,
    participant: Participant,
    global_enabled: bool,
    overrides: dict[str, bool],
) -> bool:
    participant_id = str(participant.participant_id or '').strip()
    if participant_id:
        if participant_id in overrides:
            return bool(overrides[participant_id])
        lowered = participant_id.lower()
        if lowered in overrides:
            return bool(overrides[lowered])
    return bool(global_enabled)


def resolve_model_for_participant(
    *,
    participant: Participant,
    provider_models: dict[str, str],
    participant_models: dict[str, str],
) -> str | None:
    participant_id = str(participant.participant_id or '').strip()
    if participant_id:
        exact = str(participant_models.get(participant_id) or '').strip()
        if exact:
            return exact
        lowered = str(participant_models.get(participant_id.lower()) or '').strip()
        if lowered:
            return lowered
    return str(provider_models.get(participant.provider) or '').strip() or None


def resolve_model_params_for_participant(
    *,
    participant: Participant,
    provider_model_params: dict[str, str],
    participant_model_params: dict[str, str],
) -> str | None:
    participant_id = str(participant.participant_id or '').strip()
    if participant_id:
        exact = str(participant_model_params.get(participant_id) or '').strip()
        if exact:
            return exact
        lowered = str(participant_model_params.get(participant_id.lower()) or '').strip()
        if lowered:
            return lowered
    return str(provider_model_params.get(participant.provider) or '').strip() or None


def normalize_repair_mode(value: str | None) -> str:
    mode = str(value or '').strip().lower()
    if mode in {'minimal', 'balanced', 'structural'}:
        return mode
    return 'balanced'
