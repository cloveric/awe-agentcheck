from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Callable

from awe_agentcheck.policy_templates import DEFAULT_POLICY_TEMPLATE, DEFAULT_RISK_POLICY_CONTRACT


def analyze_workspace_profile(workspace_path: str | None) -> dict:
    resolved = str(workspace_path or '').strip()
    if not resolved:
        return {
            'workspace_path': '',
            'exists': False,
            'repo_size': 'unknown',
            'risk_level': 'unknown',
            'file_count': 0,
            'risk_markers': 0,
        }

    root = Path(resolved)
    if not root.exists() or not root.is_dir():
        return {
            'workspace_path': str(root),
            'exists': False,
            'repo_size': 'unknown',
            'risk_level': 'unknown',
            'file_count': 0,
            'risk_markers': 0,
        }

    ignore_dirs = {
        '.git',
        '.agents',
        '.venv',
        '__pycache__',
        '.pytest_cache',
        '.ruff_cache',
        'node_modules',
    }
    risk_tokens = {
        'prod',
        'deploy',
        'k8s',
        'terraform',
        'helm',
        'security',
        'auth',
        'payment',
        'migrations',
        'migration',
        'database',
        'db',
    }
    risk_extensions = {'.sql', '.tf', '.yaml', '.yml'}

    file_count = 0
    risk_markers = 0
    max_scan = 5000
    for path in root.rglob('*'):
        if file_count >= max_scan:
            break
        if not path.is_file():
            continue
        rel_parts = path.relative_to(root).parts
        if any(part in ignore_dirs for part in rel_parts):
            continue
        file_count += 1
        rel_text = '/'.join(str(v).lower() for v in rel_parts)
        stem = path.stem.lower()
        ext = path.suffix.lower()
        if any(token in rel_text for token in risk_tokens):
            risk_markers += 1
            continue
        if ext in risk_extensions and stem in {'prod', 'deploy', 'migration', 'schema', 'security'}:
            risk_markers += 1

    if file_count <= 120:
        repo_size = 'small'
    elif file_count <= 1200:
        repo_size = 'medium'
    else:
        repo_size = 'large'

    if risk_markers >= 20 or (repo_size == 'large' and risk_markers >= 8):
        risk_level = 'high'
    elif risk_markers >= 6 or repo_size == 'large':
        risk_level = 'medium'
    else:
        risk_level = 'low'

    return {
        'workspace_path': str(root.resolve()),
        'exists': True,
        'repo_size': repo_size,
        'risk_level': risk_level,
        'file_count': file_count,
        'risk_markers': risk_markers,
        'scan_truncated': file_count >= max_scan,
    }


def recommend_policy_template(*, profile: dict) -> str:
    return DEFAULT_POLICY_TEMPLATE


def risk_contract_file_candidates(project_root: Path) -> list[Path]:
    root = Path(project_root)
    return [
        root / 'ops' / 'risk_policy_contract.json',
        root / '.agents' / 'risk_policy_contract.json',
    ]


def normalize_required_checks(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in value:
        item = str(raw or '').strip()
        if not item:
            continue
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        out.append(item)
    return out


def load_risk_policy_contract(*, project_root: Path) -> dict[str, object]:
    contract: dict[str, object] = dict(DEFAULT_RISK_POLICY_CONTRACT)
    merge_policy_raw = contract.get('mergePolicy')
    merge_policy: dict[str, dict[str, object]]
    if isinstance(merge_policy_raw, dict):
        merge_policy = {
            str(key): (value if isinstance(value, dict) else {})
            for key, value in merge_policy_raw.items()
        }
    else:
        merge_policy = {}
    contract['mergePolicy'] = merge_policy
    for candidate in risk_contract_file_candidates(project_root):
        if not candidate.exists() or not candidate.is_file():
            continue
        try:
            parsed = json.loads(candidate.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(parsed, dict):
            continue
        candidate_merge = parsed.get('mergePolicy')
        if isinstance(candidate_merge, dict):
            normalized_merge: dict[str, dict[str, object]] = {}
            for tier_key, tier_payload in candidate_merge.items():
                tier = str(tier_key or '').strip().lower()
                payload = tier_payload if isinstance(tier_payload, dict) else {}
                normalized_merge[tier] = {
                    **payload,
                    'requiredChecks': normalize_required_checks(payload.get('requiredChecks')),
                }
            merge_policy = normalized_merge
        contract = {
            'version': str(parsed.get('version') or contract.get('version') or '1'),
            'riskTierRules': parsed.get('riskTierRules', contract.get('riskTierRules', {})),
            'mergePolicy': merge_policy,
            'source_path': str(candidate),
        }
        return contract

    contract['source_path'] = 'builtin'
    if isinstance(merge_policy, dict):
        normalized_merge_default: dict[str, dict[str, object]] = {}
        for tier_key, tier_payload in merge_policy.items():
            tier = str(tier_key or '').strip().lower()
            payload = tier_payload if isinstance(tier_payload, dict) else {}
            normalized_merge_default[tier] = {
                **payload,
                'requiredChecks': normalize_required_checks(payload.get('requiredChecks')),
            }
        contract['mergePolicy'] = normalized_merge_default
    return contract


def resolve_risk_tier_from_profile(profile: dict) -> str:
    risk_level = str(profile.get('risk_level') or '').strip().lower()
    if risk_level == 'high':
        return 'high'
    return 'low'


def requires_browser_evidence(*, title: str, description: str) -> bool:
    haystack = f'{title}\n{description}'.lower()
    return bool(re.search(r'\b(ui|frontend|browser|page|screen|dashboard|web)\b', haystack))


def run_preflight_risk_gate(
    *,
    row: dict,
    workspace_root: Path,
    read_git_head_sha_fn: Callable[[Path | None], str | None],
) -> dict[str, object]:
    project_root = Path(str(row.get('project_path') or row.get('workspace_path') or workspace_root))
    profile = analyze_workspace_profile(str(project_root))
    tier = resolve_risk_tier_from_profile(profile)
    contract = load_risk_policy_contract(project_root=project_root)
    merge_policy = contract.get('mergePolicy')
    merge_policy_map = merge_policy if isinstance(merge_policy, dict) else {}
    tier_policy = merge_policy_map.get(tier)
    tier_policy_map = tier_policy if isinstance(tier_policy, dict) else {}
    required_checks = normalize_required_checks(tier_policy_map.get('requiredChecks'))

    test_command = str(row.get('test_command') or '').strip()
    lint_command = str(row.get('lint_command') or '').strip()
    reviewers = list(row.get('reviewer_participants') or [])
    title = str(row.get('title') or '').strip()
    description = str(row.get('description') or '').strip()
    project_has_git = bool((project_root / '.git').exists())
    head_probe_root = project_root if project_has_git else workspace_root
    head_sha = read_git_head_sha_fn(head_probe_root)
    head_gate_ok = (not project_has_git) or bool(head_sha)

    check_values = {
        'risk-policy-gate': True,
        'harness-smoke': bool(test_command) and bool(lint_command),
        'ci-pipeline': bool(test_command) and bool(lint_command),
        'head-sha-gate': head_gate_ok,
        'review-head-sha-gate': head_gate_ok,
        'evidence-manifest': True,
        'browser evidence': (
            (not requires_browser_evidence(title=title, description=description))
            or ('playwright' in test_command.lower())
            or ('browser' in test_command.lower())
        ),
    }

    failed_required: list[str] = []
    for check_name in required_checks:
        lookup = str(check_name or '').strip().lower()
        if not lookup:
            continue
        ok = bool(check_values.get(lookup, False))
        if not ok:
            failed_required.append(check_name)

    if not reviewers:
        failed_required.append('reviewers_present')

    if not test_command:
        failed_required.append('test_command_present')
    if not lint_command:
        failed_required.append('lint_command_present')

    seen_failed: set[str] = set()
    unique_failed: list[str] = []
    for item in failed_required:
        key = str(item or '').strip().lower()
        if not key or key in seen_failed:
            continue
        seen_failed.add(key)
        unique_failed.append(str(item))

    passed = len(unique_failed) == 0
    reason = 'passed' if passed else 'preflight_risk_gate_failed'
    return {
        'passed': passed,
        'reason': reason,
        'risk_tier': tier,
        'required_checks': required_checks,
        'failed_checks': unique_failed,
        'profile': profile,
        'contract_version': str(contract.get('version') or '1'),
        'contract_source': str(contract.get('source_path') or 'builtin'),
        'head_sha': head_sha,
    }
