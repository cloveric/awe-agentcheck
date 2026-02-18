from __future__ import annotations

import json
from pathlib import Path
import zipfile

from awe_agentcheck.fusion import AutoFusionManager


def test_build_manifest_ignores_cache_and_git_dirs(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "keep.txt").write_text("ok\n", encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("secret\n", encoding="utf-8")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "x.pyc").write_bytes(b"123")

    mgr = AutoFusionManager(snapshot_root=tmp_path / "snapshots")
    manifest = mgr.build_manifest(root)

    assert "keep.txt" in manifest
    assert ".git/config" not in manifest
    assert "__pycache__/x.pyc" not in manifest


def test_run_cross_repo_auto_fusion_copies_deletes_changelog_and_snapshot(tmp_path: Path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()

    (source / "a.txt").write_text("v1\n", encoding="utf-8")
    (source / "b.txt").write_text("keep then delete\n", encoding="utf-8")
    (target / "b.txt").write_text("stale\n", encoding="utf-8")

    mgr = AutoFusionManager(snapshot_root=tmp_path / "snapshots")
    before = mgr.build_manifest(source)

    (source / "a.txt").write_text("v2\n", encoding="utf-8")
    (source / "b.txt").unlink()
    (source / "c.txt").write_text("new\n", encoding="utf-8")

    result = mgr.run(
        task_id="task-1",
        source_root=source,
        target_root=target,
        before_manifest=before,
    )

    assert (target / "a.txt").read_text(encoding="utf-8") == "v2\n"
    assert (target / "c.txt").read_text(encoding="utf-8") == "new\n"
    assert not (target / "b.txt").exists()
    assert result.mode == "cross_repo"
    assert "a.txt" in result.changed_files
    assert "b.txt" in result.deleted_files
    assert "a.txt" in result.copied_files

    changelog = Path(result.changelog_path)
    assert changelog.exists()
    assert "task-1" in changelog.read_text(encoding="utf-8")

    snapshot = Path(result.snapshot_path)
    assert snapshot.exists()
    with zipfile.ZipFile(snapshot, "r") as zf:
        meta = json.loads(zf.read("meta.json").decode("utf-8"))
        assert meta["task_id"] == "task-1"
        assert "a.txt" in meta["changed_files"]


def test_run_in_place_no_changes_returns_no_changes_mode(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.txt").write_text("same\n", encoding="utf-8")

    mgr = AutoFusionManager(snapshot_root=tmp_path / "snapshots")
    before = mgr.build_manifest(source)
    result = mgr.run(
        task_id="task-2",
        source_root=source,
        target_root=source,
        before_manifest=before,
    )
    assert result.mode == "no_changes"
    assert result.changed_files == []
    assert result.snapshot_path == ""
    assert result.changelog_path == ""


def test_hash_file_uses_stable_sha256_hex(tmp_path: Path):
    file_path = tmp_path / "payload.txt"
    file_path.write_text("same\n", encoding="utf-8")

    digest_1 = AutoFusionManager._hash_file(file_path)
    digest_2 = AutoFusionManager._hash_file(file_path)

    assert digest_1 == digest_2
    assert len(digest_1) == 64
    assert all(ch in "0123456789abcdef" for ch in digest_1)


def test_hash_file_changes_when_content_changes(tmp_path: Path):
    file_path = tmp_path / "payload.txt"
    file_path.write_text("v1\n", encoding="utf-8")
    digest_1 = AutoFusionManager._hash_file(file_path)

    file_path.write_text("v2\n", encoding="utf-8")
    digest_2 = AutoFusionManager._hash_file(file_path)

    assert digest_1 != digest_2
