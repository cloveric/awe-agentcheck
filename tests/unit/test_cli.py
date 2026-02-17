from __future__ import annotations

from awe_agentcheck.cli import build_parser


def test_cli_parser_run_subcommand_accepts_author_and_reviewers():
    parser = build_parser()
    args = parser.parse_args(
        [
            'run',
            '--task',
            'Implement feature X',
            '--author',
            'claude#author-A',
            '--reviewer',
            'codex#review-B',
            '--reviewer',
            'claude#review-C',
            '--evolution-level',
            '2',
            '--evolve-until',
            '2026-02-13 06:00',
            '--conversation-language',
            'zh',
            '--sandbox-mode',
            '1',
            '--sandbox-workspace-path',
            'C:/Users/hangw/awe-agentcheck-lab',
            '--self-loop-mode',
            '0',
            '--provider-model',
            'claude=claude-sonnet-4-5',
            '--provider-model',
            'codex=gpt-5-codex',
            '--provider-model-param',
            'codex=-c model_reasoning_effort=high',
            '--claude-team-agents',
            '1',
            '--merge-target-path',
            'C:/Users/hangw/awe-agentcheck',
        ]
    )

    assert args.command == 'run'
    assert args.author == 'claude#author-A'
    assert args.reviewer == ['codex#review-B', 'claude#review-C']
    assert args.evolution_level == 2
    assert args.evolve_until == '2026-02-13 06:00'
    assert args.conversation_language == 'zh'
    assert args.sandbox_mode == 1
    assert args.sandbox_workspace_path == 'C:/Users/hangw/awe-agentcheck-lab'
    assert args.self_loop_mode == 0
    assert args.provider_model == ['claude=claude-sonnet-4-5', 'codex=gpt-5-codex']
    assert args.provider_model_param == ['codex=-c model_reasoning_effort=high']
    assert args.claude_team_agents == 1
    assert args.auto_merge is True
    assert args.merge_target_path == 'C:/Users/hangw/awe-agentcheck'


def test_cli_parser_run_supports_disabling_auto_merge():
    parser = build_parser()
    args = parser.parse_args(
        [
            'run',
            '--task',
            'Task',
            '--author',
            'claude#author-A',
            '--reviewer',
            'codex#review-B',
            '--no-auto-merge',
        ]
    )
    assert args.auto_merge is False


def test_cli_parser_supports_start_command():
    parser = build_parser()
    args = parser.parse_args(['start', 'task-1', '--background'])
    assert args.command == 'start'
    assert args.task_id == 'task-1'
    assert args.background is True


def test_cli_parser_supports_stats_command():
    parser = build_parser()
    args = parser.parse_args(['stats'])
    assert args.command == 'stats'


def test_cli_parser_supports_force_fail_command():
    parser = build_parser()
    args = parser.parse_args(['force-fail', 'task-1', '--reason', 'watchdog_timeout'])
    assert args.command == 'force-fail'
    assert args.task_id == 'task-1'
    assert args.reason == 'watchdog_timeout'


def test_cli_parser_supports_tree_command():
    parser = build_parser()
    args = parser.parse_args(['tree', '--workspace-path', 'C:/repo', '--max-depth', '3', '--max-entries', '120'])
    assert args.command == 'tree'
    assert args.workspace_path == 'C:/repo'
    assert args.max_depth == 3
    assert args.max_entries == 120


def test_cli_parser_supports_author_decide_command():
    parser = build_parser()
    args = parser.parse_args(['decide', 'task-7', '--approve', '--note', 'ship', '--auto-start'])
    assert args.command == 'decide'
    assert args.task_id == 'task-7'
    assert args.approve is True
    assert args.note == 'ship'
    assert args.auto_start is True
