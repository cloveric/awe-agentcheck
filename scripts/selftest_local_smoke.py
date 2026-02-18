from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys
import time

import httpx


TERMINAL_STATUSES = {"passed", "failed_gate", "failed_system", "canceled"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a local dry-run end-to-end smoke test against awe-agentcheck itself."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8011)
    parser.add_argument("--health-timeout-seconds", type=int, default=30)
    parser.add_argument("--task-timeout-seconds", type=int, default=90)
    return parser


def wait_for_health(api_base: str, timeout_seconds: int) -> None:
    deadline = time.monotonic() + max(1, int(timeout_seconds))
    last_error = ""
    while time.monotonic() < deadline:
        try:
            with httpx.Client(timeout=3) as client:
                resp = client.get(f"{api_base}/healthz")
                if resp.status_code == 200:
                    return
                last_error = f"healthz returned {resp.status_code}"
        except Exception as exc:  # pragma: no cover - exercised by runtime only
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"health check failed within {timeout_seconds}s: {last_error}")


def run_smoke(*, api_base: str, workspace_path: str, task_timeout_seconds: int) -> dict:
    payload = {
        "title": "Selftest: monitor pipeline",
        "description": "Run full flow in dry-run mode for self verification",
        "author_participant": "claude#author-A",
        "reviewer_participants": ["codex#review-B"],
        "workspace_path": workspace_path,
        "max_rounds": 2,
        "self_loop_mode": 0,
        "test_command": "py -m pytest -q",
        "lint_command": "py -m ruff check .",
        "auto_start": True,
    }

    with httpx.Client(timeout=20) as client:
        index = client.get(f"{api_base}/")
        index.raise_for_status()
        index_text = index.text
        for marker in ('id="projectTree"', 'id="projectSelect"', 'id="roleList"', 'id="dialogue"'):
            if marker not in index_text:
                raise RuntimeError(f"monitor layout marker missing: {marker}")

        created = client.post(f"{api_base}/api/tasks", json=payload)
        created.raise_for_status()
        task = created.json()
        task_id = str(task["task_id"])

        deadline = time.monotonic() + max(1, int(task_timeout_seconds))
        final = task
        approved_manual = False
        while time.monotonic() < deadline:
            resp = client.get(f"{api_base}/api/tasks/{task_id}")
            resp.raise_for_status()
            final = resp.json()
            status = str(final.get("status", ""))
            if status == "waiting_manual" and not approved_manual:
                decision = client.post(
                    f"{api_base}/api/tasks/{task_id}/author-decision",
                    json={
                        "approve": True,
                        "note": "selftest auto approve waiting_manual proposal",
                        "auto_start": True,
                    },
                )
                decision.raise_for_status()
                approved_manual = True
                time.sleep(1)
                continue
            if status in TERMINAL_STATUSES:
                break
            time.sleep(1)
        else:
            raise RuntimeError(f"task {task_id} did not reach terminal status in {task_timeout_seconds}s")

        if str(final.get("status")) != "passed":
            raise RuntimeError(
                f"selftest task did not pass: status={final.get('status')} reason={final.get('last_gate_reason')}"
            )

        events = client.get(f"{api_base}/api/tasks/{task_id}/events")
        events.raise_for_status()
        rows = events.json()
        if not any(str(row.get("type")) == "gate_passed" for row in rows):
            raise RuntimeError(f"task {task_id} missing gate_passed event")

        stats = client.get(f"{api_base}/api/stats")
        stats.raise_for_status()
        stats_body = stats.json()
        if int(stats_body.get("total_tasks", 0)) < 1:
            raise RuntimeError("stats total_tasks is unexpectedly zero")

        return {
            "task_id": task_id,
            "status": final.get("status"),
            "rounds_completed": final.get("rounds_completed"),
            "events": len(rows),
            "stats_total_tasks": stats_body.get("total_tasks"),
            "pass_rate_50": stats_body.get("pass_rate_50"),
            "manual_approval_used": approved_manual,
        }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = Path(__file__).resolve().parents[1]
    api_base = f"http://{args.host}:{args.port}"

    log_dir = repo / ".agents" / "selftest"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    stdout_path = log_dir / f"selftest-api-{stamp}.stdout.log"
    stderr_path = log_dir / f"selftest-api-{stamp}.stderr.log"

    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo / "src")
    env["AWE_DRY_RUN"] = "true"
    env["AWE_DATABASE_URL"] = "invalid+driver://fallback"
    env["AWE_ARTIFACT_ROOT"] = str(repo / ".agents" / "selftest-artifacts" / stamp)
    env["AWE_MAX_CONCURRENT_RUNNING_TASKS"] = "1"

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "awe_agentcheck.main:app",
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]

    with stdout_path.open("w", encoding="utf-8") as out, stderr_path.open("w", encoding="utf-8") as err:
        proc = subprocess.Popen(
            cmd,
            cwd=str(repo),
            env=env,
            stdout=out,
            stderr=err,
            text=True,
        )
        try:
            wait_for_health(api_base, timeout_seconds=args.health_timeout_seconds)
            summary = run_smoke(
                api_base=api_base,
                workspace_path=str(repo),
                task_timeout_seconds=args.task_timeout_seconds,
            )
            print("SELFTEST_OK")
            for key, value in summary.items():
                print(f"{key}={value}")
            print(f"api_stdout={stdout_path}")
            print(f"api_stderr={stderr_path}")
            return 0
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
