from awe_agentcheck.participants import parse_participant_id, register_provider, set_extra_providers


def test_parse_participant_id_with_role_suffix():
    p = parse_participant_id('claude#author-A')
    assert p.provider == 'claude'
    assert p.alias == 'author-A'


def test_parse_participant_id_supports_gemini_provider():
    p = parse_participant_id('gemini#review-X')
    assert p.provider == 'gemini'
    assert p.alias == 'review-X'


def test_parse_participant_id_requires_hash_separator():
    try:
        parse_participant_id('claude-author')
    except ValueError as exc:
        assert 'provider#alias' in str(exc)
    else:
        raise AssertionError('expected ValueError')


def test_parse_participant_id_supports_registered_extra_provider():
    set_extra_providers(set())
    register_provider('qwen')
    p = parse_participant_id('qwen#review-Z')
    assert p.provider == 'qwen'
    assert p.alias == 'review-Z'
    set_extra_providers(set())
