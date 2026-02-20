from __future__ import annotations

import pytest

from awe_agentcheck import participants


def test_set_extra_providers_normalization_and_filtering():
    participants.set_extra_providers({'Qwen', 'deepseek', '', 'bad#name'})
    supported = participants.get_supported_providers()
    assert 'qwen' in supported
    assert 'deepseek' in supported
    assert 'bad#name' not in supported

    participants.set_extra_providers(None)
    supported2 = participants.get_supported_providers()
    assert 'qwen' not in supported2
    assert 'claude' in supported2
    assert 'codex' in supported2
    assert 'gemini' in supported2


def test_register_provider_valid_and_invalid():
    participants.set_extra_providers(None)
    participants.register_provider('Qwen')
    assert 'qwen' in participants.get_supported_providers()
    participants.register_provider('claude')
    assert 'claude' in participants.get_supported_providers()

    with pytest.raises(ValueError):
        participants.register_provider('')
    with pytest.raises(ValueError):
        participants.register_provider('bad#name')


def test_parse_participant_id_validation():
    participants.set_extra_providers({'qwen'})
    parsed = participants.parse_participant_id('qwen#review-A')
    assert parsed.provider == 'qwen'
    assert parsed.alias == 'review-A'

    with pytest.raises(ValueError):
        participants.parse_participant_id('no-hash')
    with pytest.raises(ValueError):
        participants.parse_participant_id('unknown#x')
    with pytest.raises(ValueError):
        participants.parse_participant_id('codex#')
