from __future__ import annotations

from importlib import import_module, metadata

from awe_agentcheck.cli import main


def test_console_script_entrypoint_resolves_to_cli_main():
    distribution = metadata.distribution('awe-agentcheck')
    entrypoints = {entry.name: entry for entry in distribution.entry_points}

    assert 'awe-agentcheck' in entrypoints
    entry = entrypoints['awe-agentcheck']
    assert entry.value == 'awe_agentcheck.cli:main'
    assert entry.load() is main


def test_storage_and_db_modules_are_importable():
    storage_module = import_module('awe_agentcheck.storage.artifacts')
    db_module = import_module('awe_agentcheck.db')

    assert hasattr(storage_module, 'ArtifactStore')
    assert hasattr(db_module, 'Database')
