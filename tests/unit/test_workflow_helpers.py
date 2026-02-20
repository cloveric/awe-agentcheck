from __future__ import annotations

from pathlib import Path

import pytest

from awe_agentcheck.participants import parse_participant_id
from awe_agentcheck.workflow_prompting import (
    inject_prompt_extras,
    load_prompt_template,
    render_prompt_template,
)
from awe_agentcheck.workflow_runtime import (
    normalize_participant_agent_overrides,
    normalize_participant_model_params,
    normalize_participant_models,
    normalize_provider_model_params,
    normalize_provider_models,
    normalize_repair_mode,
    resolve_agent_toggle_for_participant,
    resolve_model_for_participant,
    resolve_model_params_for_participant,
)
from awe_agentcheck.workflow_text import clip_text, text_signature


def test_prompt_injection_and_template_loading(tmp_path: Path):
    assert inject_prompt_extras(base='hello', environment_context=None, strategy_hint=None) == 'hello'
    assert inject_prompt_extras(
        base='hello',
        environment_context='ENV: repo tree',
        strategy_hint='switch to root-cause',
    ).endswith('Strategy shift hint: switch to root-cause')

    template_dir = tmp_path / 'templates'
    template_dir.mkdir(parents=True, exist_ok=True)
    (template_dir / 'review.txt').write_text('Task=$task_id Verdict=$verdict Missing=$missing', encoding='utf-8')

    cache = {}
    first = load_prompt_template(template_name='review.txt', template_dir=template_dir, cache=cache)
    second = load_prompt_template(template_name='review.txt', template_dir=template_dir, cache=cache)
    assert first is second

    rendered = render_prompt_template(
        template_name='review.txt',
        template_dir=template_dir,
        cache=cache,
        fields={'task_id': 'task-1', 'verdict': 'NO_BLOCKER', 'missing': None},
    )
    assert rendered == 'Task=task-1 Verdict=NO_BLOCKER Missing='

    with pytest.raises(ValueError):
        load_prompt_template(template_name='../escape.txt', template_dir=template_dir, cache=cache)
    with pytest.raises(ValueError):
        load_prompt_template(template_name='', template_dir=template_dir, cache=cache)


def test_workflow_runtime_normalizers_and_resolution():
    provider_models = normalize_provider_models({' Codex ': 'gpt-5.3-codex', '': 'x'})
    assert provider_models == {'codex': 'gpt-5.3-codex'}
    provider_params = normalize_provider_model_params({'claude': '--temperature 0.2', '  ': 'x'})
    assert provider_params == {'claude': '--temperature 0.2'}

    participant_models = normalize_participant_models({'Codex#Author-A': 'gpt-5.3-codex', '': 'x'})
    assert participant_models['Codex#Author-A'] == 'gpt-5.3-codex'
    assert participant_models['codex#author-a'] == 'gpt-5.3-codex'
    participant_params = normalize_participant_model_params({'Codex#Author-A': '-c model_reasoning_effort=xhigh'})
    assert participant_params['codex#author-a'].endswith('xhigh')

    overrides = normalize_participant_agent_overrides({'Codex#Author-A': 'on', '': False})
    assert overrides['codex#author-a'] is True
    participant = parse_participant_id('codex#author-A')
    assert resolve_agent_toggle_for_participant(
        participant=participant,
        global_enabled=False,
        overrides=overrides,
    ) is True

    assert resolve_model_for_participant(
        participant=participant,
        provider_models=provider_models,
        participant_models=participant_models,
    ) == 'gpt-5.3-codex'

    assert resolve_model_params_for_participant(
        participant=participant,
        provider_model_params=provider_params,
        participant_model_params=participant_params,
    ) == '-c model_reasoning_effort=xhigh'

    missing_participant = parse_participant_id('claude#review-B')
    assert resolve_model_params_for_participant(
        participant=missing_participant,
        provider_model_params={},
        participant_model_params={},
    ) is None

    assert normalize_repair_mode('minimal') == 'minimal'
    assert normalize_repair_mode('unknown') == 'balanced'


def test_workflow_text_helpers():
    assert clip_text('abc', max_chars=10) == 'abc'
    clipped = clip_text('x' * 12, max_chars=4)
    assert clipped.startswith('xxxx')
    assert '[truncated' in clipped

    assert text_signature('') == ''
    assert text_signature('Hello   World') == text_signature('hello world')
    long_sig = text_signature('A' * 2000, max_chars=20)
    assert len(long_sig) == 16
