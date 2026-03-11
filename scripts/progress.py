#!/usr/bin/env python3
"""
Progress tracker for repogen repository generation.

Usage:
  python scripts/progress.py init                        # (Re)init from matrix.yaml
  python scripts/progress.py status                      # Show status table
  python scripts/progress.py set <name> <status>         # Update repo status
  python scripts/progress.py set <name> done --verified  # Mark done + verified
  python scripts/progress.py reset <name>                # Reset to pending
  python scripts/progress.py pending                     # Print pending repo names
  python scripts/progress.py done                        # Print done repo names
  python scripts/progress.py failed                      # Print failed repo names

Status values: pending | in-progress | done | failed
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("Error: PyYAML required. Install with: pip install pyyaml")

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
MATRIX_PATH = ROOT / "matrix.yaml"
PROGRESS_PATH = ROOT / "progress.yaml"

STATUSES = ("pending", "in-progress", "done", "failed")


def load_progress() -> dict:
    if not PROGRESS_PATH.exists():
        return {"repos": {}}
    with open(PROGRESS_PATH) as f:
        return yaml.safe_load(f) or {"repos": {}}


def save_progress(data: dict) -> None:
    with open(PROGRESS_PATH, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def load_matrix_names() -> list:
    if not MATRIX_PATH.exists():
        sys.exit(f"Error: {MATRIX_PATH} not found. Run: repogen init --spec <spec> --langs languages.yaml")
    with open(MATRIX_PATH) as f:
        data = yaml.safe_load(f)
    return [r["name"] for r in data.get("repos", [])]


def cmd_init(args) -> None:
    names = load_matrix_names()
    existing = load_progress()
    repos = existing.setdefault("repos", {})
    added = 0
    for name in names:
        if name not in repos:
            repos[name] = {"status": "pending", "generated_at": None, "verified": False}
            added += 1
    save_progress(existing)
    print(f"Initialized: {added} new repo(s) added to {PROGRESS_PATH}")
    if added == 0:
        print("(All repos already tracked — use 'reset <name>' to clear individual entries)")


def cmd_status(args) -> None:
    data = load_progress()
    repos = data.get("repos", {})
    if not repos:
        print("No repos tracked. Run: python scripts/progress.py init")
        return

    counts = {s: 0 for s in STATUSES}
    print(f"{'Repo':<40} {'Status':<12} {'Generated':<26} {'Verified'}")
    print("-" * 90)
    for name, info in repos.items():
        status = info.get("status", "pending")
        gen = str(info.get("generated_at") or "-")[:25]
        verified = "yes" if info.get("verified") else "no"
        print(f"{name:<40} {status:<12} {gen:<26} {verified}")
        counts[status] = counts.get(status, 0) + 1
    print("-" * 90)
    total = len(repos)
    parts = [f"{s}: {counts[s]}" for s in STATUSES if counts[s] > 0]
    print(f"Total: {total}  |  " + "  |  ".join(parts))


def cmd_set(args) -> None:
    data = load_progress()
    repos = data.setdefault("repos", {})
    name = args.name
    status = args.status
    if name not in repos:
        repos[name] = {"status": "pending", "generated_at": None, "verified": False}
    repos[name]["status"] = status
    if status in ("done", "failed", "in-progress"):
        repos[name]["generated_at"] = datetime.now(timezone.utc).isoformat()
    if status == "done" and getattr(args, "verified", False):
        repos[name]["verified"] = True
    save_progress(data)
    verified_note = " (verified)" if getattr(args, "verified", False) else ""
    print(f"Updated: {name} → {status}{verified_note}")


def cmd_reset(args) -> None:
    data = load_progress()
    repos = data.setdefault("repos", {})
    repos[args.name] = {"status": "pending", "generated_at": None, "verified": False}
    save_progress(data)
    print(f"Reset: {args.name} → pending")


def cmd_list(args) -> None:
    data = load_progress()
    repos = data.get("repos", {})
    for name, info in repos.items():
        if info.get("status") == args.filter_status:
            print(name)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage repogen repository generation progress",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="(Re)initialize from matrix.yaml")
    sub.add_parser("status", help="Show status table")

    p_set = sub.add_parser("set", help="Set repo status")
    p_set.add_argument("name", help="Repo name (e.g. crud-python-fastapi)")
    p_set.add_argument("status", choices=list(STATUSES))
    p_set.add_argument("--verified", action="store_true", help="Also mark as verified")

    p_reset = sub.add_parser("reset", help="Reset a repo to pending")
    p_reset.add_argument("name")

    p_pending = sub.add_parser("pending", help="Print pending repo names")
    p_pending.set_defaults(filter_status="pending")

    p_done = sub.add_parser("done", help="Print done repo names")
    p_done.set_defaults(filter_status="done")

    p_failed = sub.add_parser("failed", help="Print failed repo names")
    p_failed.set_defaults(filter_status="failed")

    args = parser.parse_args()

    dispatch = {
        "init": cmd_init,
        "status": cmd_status,
        "set": cmd_set,
        "reset": cmd_reset,
        "pending": cmd_list,
        "done": cmd_list,
        "failed": cmd_list,
    }
    dispatch[args.cmd](args)


if __name__ == "__main__":
    main()
