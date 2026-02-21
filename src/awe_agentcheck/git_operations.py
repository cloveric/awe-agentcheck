from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess


def run_git_command(*, root: Path, args: list[str]) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            ['git', *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False, ''
    if completed.returncode != 0:
        return False, (completed.stderr or completed.stdout or '').strip()
    return True, (completed.stdout or '').strip()


def read_git_head_sha(root: Path | None) -> str | None:
    if root is None:
        return None
    target = Path(root)
    if not target.exists() or not target.is_dir():
        return None
    ok, payload = run_git_command(root=target, args=['rev-parse', 'HEAD'])
    if not ok:
        return None
    sha = str(payload or '').strip()
    if re.fullmatch(r'[0-9a-fA-F]{40}', sha):
        return sha.lower()
    return None


def read_git_state(root: Path | None) -> dict:
    if root is None:
        return {
            'is_git_repo': False,
            'branch': None,
            'worktree_clean': None,
            'remote_origin': None,
            'guard_allowed': True,
            'guard_reason': 'no_target',
        }
    if not root.exists() or not root.is_dir():
        return {
            'is_git_repo': False,
            'branch': None,
            'worktree_clean': None,
            'remote_origin': None,
            'guard_allowed': True,
            'guard_reason': 'missing_path',
        }

    ok_git, git_flag = run_git_command(root=root, args=['rev-parse', '--is-inside-work-tree'])
    if not ok_git or git_flag.strip().lower() != 'true':
        return {
            'is_git_repo': False,
            'branch': None,
            'worktree_clean': None,
            'remote_origin': None,
            'guard_allowed': True,
            'guard_reason': 'non_git_repo',
        }

    ok_branch, branch = run_git_command(root=root, args=['branch', '--show-current'])
    ok_status, status_out = run_git_command(root=root, args=['status', '--porcelain'])
    ok_remote, remote = run_git_command(root=root, args=['remote', 'get-url', 'origin'])
    return {
        'is_git_repo': True,
        'branch': branch if ok_branch else None,
        'worktree_clean': (len(str(status_out or '').strip()) == 0) if ok_status else None,
        'remote_origin': remote if ok_remote else None,
        'guard_allowed': True,
        'guard_reason': 'unvalidated',
    }


def promotion_guard_config() -> dict:
    enabled = str(os.getenv('AWE_PROMOTION_GUARD_ENABLED', '1') or '1').strip().lower() in {'1', 'true', 'yes', 'on'}
    # Default is non-blocking for local development; enforce via env when needed.
    require_clean = str(os.getenv('AWE_PROMOTION_REQUIRE_CLEAN', '0') or '0').strip().lower() in {'1', 'true', 'yes', 'on'}
    raw_branches = str(os.getenv('AWE_PROMOTION_ALLOWED_BRANCHES', '') or '').strip()
    allowed_branches = [
        item.strip()
        for item in raw_branches.split(',')
        if item.strip()
    ]
    return {
        'enabled': enabled,
        'require_clean': require_clean,
        'allowed_branches': allowed_branches,
    }


def evaluate_promotion_guard(*, target_root: Path) -> dict:
    cfg = promotion_guard_config()
    git = read_git_state(target_root)
    payload = {
        'enabled': bool(cfg.get('enabled', True)),
        'target_path': str(target_root),
        'allowed_branches': list(cfg.get('allowed_branches', [])),
        'require_clean': bool(cfg.get('require_clean', True)),
        **git,
    }
    if not payload['enabled']:
        payload['guard_allowed'] = True
        payload['guard_reason'] = 'guard_disabled'
        return payload
    if not bool(payload.get('is_git_repo')):
        payload['guard_allowed'] = True
        payload['guard_reason'] = 'non_git_repo'
        return payload
    branch = str(payload.get('branch') or '').strip()
    allowed_branches = payload.get('allowed_branches') or []
    if allowed_branches and branch and branch not in allowed_branches:
        payload['guard_allowed'] = False
        payload['guard_reason'] = f'branch_not_allowed:{branch}'
        return payload
    if bool(payload.get('require_clean')) and payload.get('worktree_clean') is False:
        payload['guard_allowed'] = False
        payload['guard_reason'] = 'dirty_worktree'
        return payload
    payload['guard_allowed'] = True
    payload['guard_reason'] = 'ok'
    return payload
