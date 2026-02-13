from __future__ import annotations

import json
from pathlib import Path

from awe_agentcheck.storage.artifacts import ArtifactStore


def test_create_task_workspace_creates_expected_files(tmp_path: Path):
    store = ArtifactStore(root=tmp_path)

    workspace = store.create_task_workspace(task_id='task-123')

    assert workspace.root.exists()
    assert workspace.discussion_md.exists()
    assert workspace.summary_md.exists()
    assert workspace.final_report_md.exists()
    assert workspace.state_json.exists()
    assert workspace.decisions_json.exists()
    assert workspace.events_jsonl.exists()
    assert workspace.artifacts_dir.exists()

    state = json.loads(workspace.state_json.read_text(encoding='utf-8'))
    assert state['task_id'] == 'task-123'
    assert state['status'] == 'queued'


def test_write_artifact_json_writes_named_payload(tmp_path: Path):
    store = ArtifactStore(root=tmp_path)
    store.create_task_workspace(task_id='task-abc')
    path = store.write_artifact_json('task-abc', name='fusion_summary', payload={'ok': True})
    assert path.exists()
    payload = json.loads(path.read_text(encoding='utf-8'))
    assert payload == {'ok': True}
