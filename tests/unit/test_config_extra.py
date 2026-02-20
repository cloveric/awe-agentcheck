from __future__ import annotations

import json

from awe_agentcheck.config import _env_int, _env_provider_commands, load_settings


def test_env_int_parsing_and_clamping(monkeypatch):
    monkeypatch.delenv('AWE_X_INT', raising=False)
    assert _env_int('AWE_X_INT', 5, minimum=3) == 5

    monkeypatch.setenv('AWE_X_INT', 'bad')
    assert _env_int('AWE_X_INT', 5, minimum=3) == 5

    monkeypatch.setenv('AWE_X_INT', '1')
    assert _env_int('AWE_X_INT', 5, minimum=3) == 3

    monkeypatch.setenv('AWE_X_INT', '9')
    assert _env_int('AWE_X_INT', 5, minimum=3) == 9


def test_env_provider_commands_validation(monkeypatch):
    monkeypatch.delenv('AWE_PROVIDER_ADAPTERS_JSON', raising=False)
    assert _env_provider_commands('AWE_PROVIDER_ADAPTERS_JSON') == {}

    monkeypatch.setenv('AWE_PROVIDER_ADAPTERS_JSON', 'not-json')
    assert _env_provider_commands('AWE_PROVIDER_ADAPTERS_JSON') == {}

    monkeypatch.setenv('AWE_PROVIDER_ADAPTERS_JSON', json.dumps(['not-a-dict']))
    assert _env_provider_commands('AWE_PROVIDER_ADAPTERS_JSON') == {}

    monkeypatch.setenv(
        'AWE_PROVIDER_ADAPTERS_JSON',
        json.dumps(
            {
                'Qwen': 'qwen-cli --yolo',
                '': 'skip',
                'bad#provider': 'skip',
                'gemini': '',
            }
        ),
    )
    parsed = _env_provider_commands('AWE_PROVIDER_ADAPTERS_JSON')
    assert parsed == {'qwen': 'qwen-cli --yolo'}


def test_load_settings_honors_env_and_fallbacks(monkeypatch):
    monkeypatch.setenv('AWE_DATABASE_URL', 'sqlite:///test.db')
    monkeypatch.setenv('AWE_ARTIFACT_ROOT', '.agents')
    monkeypatch.setenv('AWE_SERVICE_NAME', 'svc')
    monkeypatch.setenv('AWE_OTEL_EXPORTER_OTLP_ENDPOINT', 'http://127.0.0.1:4318/v1/traces')
    monkeypatch.setenv('AWE_DRY_RUN', '1')
    monkeypatch.setenv('AWE_CLAUDE_COMMAND', 'claude -p')
    monkeypatch.setenv('AWE_CODEX_COMMAND', 'codex exec')
    monkeypatch.setenv('AWE_GEMINI_COMMAND', 'gemini --yolo')
    monkeypatch.setenv('AWE_PARTICIPANT_TIMEOUT_SECONDS', '20')
    monkeypatch.setenv('AWE_COMMAND_TIMEOUT_SECONDS', '30')
    monkeypatch.setenv('AWE_PARTICIPANT_TIMEOUT_RETRIES', '2')
    monkeypatch.setenv('AWE_MAX_CONCURRENT_RUNNING_TASKS', '4')
    monkeypatch.setenv('AWE_WORKFLOW_BACKEND', 'classic')
    monkeypatch.setenv('AWE_PROVIDER_ADAPTERS_JSON', json.dumps({'qwen': 'qwen-cli'}))

    settings = load_settings()
    assert settings.database_url == 'sqlite:///test.db'
    assert settings.service_name == 'svc'
    assert settings.otel_endpoint and settings.otel_endpoint.startswith('http://')
    assert settings.dry_run is True
    assert settings.claude_command == 'claude -p'
    assert settings.codex_command == 'codex exec'
    assert settings.gemini_command == 'gemini --yolo'
    assert settings.participant_timeout_seconds == 20
    assert settings.command_timeout_seconds == 30
    assert settings.participant_timeout_retries == 2
    assert settings.max_concurrent_running_tasks == 4
    assert settings.workflow_backend == 'classic'
    assert settings.extra_provider_commands == {'qwen': 'qwen-cli'}

    monkeypatch.setenv('AWE_WORKFLOW_BACKEND', 'invalid')
    invalid_backend = load_settings()
    assert invalid_backend.workflow_backend == 'langgraph'
