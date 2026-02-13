from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import shutil


@dataclass
class ImportRow:
    source: Path
    target: Path
    status: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Import self-evolution markdown plans from awe-agentcheck-lab "
            "into awe-agentcheck documentation."
        )
    )
    parser.add_argument(
        "--source-root",
        default="C:/Users/hangw/awe-agentcheck-lab",
        help="Source lab repository root",
    )
    parser.add_argument(
        "--target-root",
        default="C:/Users/hangw/awe-agentcheck",
        help="Target main repository root",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without writing files",
    )
    return parser


def file_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def same_content(left: Path, right: Path) -> bool:
    if not left.exists() or not right.exists():
        return False
    return file_text(left) == file_text(right)


def collect_rows(source_plans: Path, target_plans: Path, *, dry_run: bool) -> list[ImportRow]:
    rows: list[ImportRow] = []
    for src in sorted(source_plans.glob("*.md")):
        dst = target_plans / f"lab-{src.name}"
        if dst.exists() and same_content(src, dst):
            rows.append(ImportRow(source=src, target=dst, status="unchanged"))
            continue
        status = "copied" if dst.exists() else "added"
        rows.append(ImportRow(source=src, target=dst, status=status))
        if not dry_run:
            shutil.copy2(src, dst)
    return rows


def write_index(index_path: Path, rows: list[ImportRow], *, source_root: Path, dry_run: bool) -> None:
    lines: list[str] = []
    lines.append("# Lab Evolution Import")
    lines.append("")
    lines.append(f"Generated at: `{datetime.now().isoformat(timespec='seconds')}`")
    lines.append("")
    lines.append("Source: `C:/Users/hangw/awe-agentcheck-lab/docs/plans`")
    lines.append("Target: `C:/Users/hangw/awe-agentcheck/docs/imported-lab-plans`")
    lines.append("")
    lines.append("This index records imported self-evolution plan docs from lab into main docs.")
    lines.append("")
    lines.append("| Source File | Imported File | Status |")
    lines.append("|---|---|---|")
    if not rows:
        lines.append("| (none) | (none) | no_source_files |")
    else:
        for row in rows:
            rel_source = row.source.relative_to(source_root).as_posix()
            imported_name = row.target.name
            lines.append(f"| `{rel_source}` | `docs/imported-lab-plans/{imported_name}` | `{row.status}` |")
    lines.append("")
    lines.append("Notes:")
    lines.append("1. This import is documentation-only. It does not auto-apply code changes.")
    lines.append("2. Use these plan docs as references for manual or scripted code promotion.")
    content = "\n".join(lines) + "\n"
    if not dry_run:
        index_path.write_text(content, encoding="utf-8")


def main() -> int:
    args = build_parser().parse_args()
    source_root = Path(args.source_root)
    target_root = Path(args.target_root)
    dry_run = bool(args.dry_run)

    source_plans = source_root / "docs" / "plans"
    target_plans = target_root / "docs" / "imported-lab-plans"
    index_path = target_root / "docs" / "LAB_EVOLUTION_IMPORT.md"

    if not source_plans.exists():
        print(f"[import] source plans directory missing: {source_plans}")
        return 1

    if not dry_run:
        target_plans.mkdir(parents=True, exist_ok=True)

    rows = collect_rows(source_plans, target_plans, dry_run=dry_run)
    write_index(index_path, rows, source_root=source_root, dry_run=dry_run)

    print(f"[import] source={source_plans}")
    print(f"[import] target={target_plans}")
    print(f"[import] index={index_path}")
    print(f"[import] files={len(rows)} dry_run={dry_run}")
    for row in rows:
        print(f"[import] {row.status}: {row.source.name} -> {row.target.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
