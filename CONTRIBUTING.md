# Contributing

Thanks for helping improve AWE-AgentForge.

## Development Setup

```bash
python -m pip install --upgrade pip
python -m pip install -e .[dev]
```

## Local Validation (Required)

Before opening a PR, run:

```bash
python -m ruff check .
python -m pytest -q
```

If you changed Web assets, also validate the dashboard behavior manually.

## PR Scope Rules

- Keep each PR focused on one topic.
- Include tests for behavior changes.
- Update docs when user-facing behavior changes.
- Do not commit secrets or local machine paths.

## Commit Style

Conventional-style prefixes are preferred:

- `feat:`
- `fix:`
- `refactor:`
- `docs:`
- `chore:`

## Cross-Platform Script Rule

When you change operator scripts:

- Keep PowerShell and Bash equivalents aligned.
- If you add a new `.ps1` workflow script, add the corresponding `.sh` script.
- If behavior diverges by OS, document the reason in `scripts/README.md`.

## Governance Notes

- Security bugs: follow `SECURITY.md`.
- Code ownership and review routing: see `.github/CODEOWNERS`.
