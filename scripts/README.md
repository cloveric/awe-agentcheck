# Script Matrix (PowerShell / Bash)

This repository provides paired operator scripts for Windows and Linux/macOS.

## API Lifecycle

- Windows: `scripts/start_api.ps1`, `scripts/stop_api.ps1`
- Linux/macOS: `scripts/start_api.sh`, `scripts/stop_api.sh`

## Overnight Loop Lifecycle

- Windows: `scripts/start_overnight_until_7.ps1`, `scripts/stop_overnight.ps1`, `scripts/supervise_until.ps1`
- Linux/macOS: `scripts/start_overnight_until_7.sh`, `scripts/stop_overnight.sh`, `scripts/supervise_until.sh`

## Usage Notes

- Bash scripts are intended to run via `bash scripts/<name>.sh ...` (execute bit is optional).
- PowerShell scripts are intended to run via:
  - `pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/<name>.ps1 ...`
- Keep behavior aligned across both script families.
