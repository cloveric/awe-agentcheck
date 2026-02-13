from __future__ import annotations

from fastapi.testclient import TestClient

from awe_agentcheck.main import build_app


def test_build_app_falls_back_to_in_memory_repo_on_bad_database_url(monkeypatch):
    monkeypatch.setenv('AWE_DATABASE_URL', 'invalid+driver://bad')
    app = build_app()
    client = TestClient(app)

    resp = client.get('/healthz')
    assert resp.status_code == 200
    assert resp.json()['status'] == 'ok'
