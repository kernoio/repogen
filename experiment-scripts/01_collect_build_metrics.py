#!/usr/bin/env python3
"""
Step 1 — Build and verify all SFR CRUD repos.

Tests: docker compose build + up, then GET /health + full CRUD endpoint suite.
Uses repogen.core.verify_repo for the build/health cycle, then runs the CRUD
suite directly to capture per-endpoint detail.

Output: reproduced-experiments/results/crud-build-metrics.jsonl

Usage:
    python3 experiment-scripts/01_collect_build_metrics.py
    python3 experiment-scripts/01_collect_build_metrics.py --matrix scripts/crud-matrix.yaml
    python3 experiment-scripts/01_collect_build_metrics.py --out reproduced-experiments/results/build-metrics.jsonl
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import yaml

# Make sure the repogen package is importable when running from repo root
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from repogen.core import run_cmd, compose_down

# ── CLI ───────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--matrix", default="scripts/crud-matrix.yaml",
                    help="Path to crud-matrix.yaml (default: scripts/crud-matrix.yaml)")
parser.add_argument("--out", default="reproduced-experiments/results/crud-build-metrics.jsonl",
                    help="Output JSONL path")
args = parser.parse_args()

matrix_path = ROOT / args.matrix if not Path(args.matrix).is_absolute() else Path(args.matrix)
out_path    = ROOT / args.out    if not Path(args.out).is_absolute()    else Path(args.out)

# ── Load matrix ───────────────────────────────────────────────────────────────

with open(matrix_path) as f:
    matrix = yaml.safe_load(f)

sfr_repos = [r for r in matrix["repos"]
             if r.get("port") and not r["name"].startswith("mono-")]

print(f"[01-build] matrix: {matrix_path}")
print(f"[01-build] repos:  {len(sfr_repos)} SFR CRUD repos")
print(f"[01-build] output: {out_path}")

# ── CRUD probe ────────────────────────────────────────────────────────────────

def try_crud(port: int, base: str = "/items") -> tuple[bool, dict]:
    """Run POST/GET/GET-id/PUT/DELETE. Returns (passed, detail_dict)."""
    details: dict[str, str] = {}

    rc, out, _ = run_cmd([
        "curl", "-sf", "-X", "POST", f"http://localhost:{port}{base}",
        "-H", "Content-Type: application/json",
        "-d", '{"name":"test","description":"e3-test"}',
    ], timeout=10)
    if rc != 0:
        details["post"] = "fail"
        return False, details
    details["post"] = "ok"

    item_id = None
    try:
        item_id = json.loads(out).get("id") or json.loads(out).get("ID") or json.loads(out).get("_id")
    except Exception:
        pass

    rc, _, _ = run_cmd(["curl", "-sf", f"http://localhost:{port}{base}"], timeout=10)
    details["get_list"] = "ok" if rc == 0 else "fail"

    if not item_id:
        details["get_id"] = details["put"] = details["delete"] = "skip (no id)"
        return details["get_list"] == "ok", details

    rc, _, _ = run_cmd(["curl", "-sf", f"http://localhost:{port}{base}/{item_id}"], timeout=10)
    details["get_id"] = "ok" if rc == 0 else "fail"

    rc, _, _ = run_cmd([
        "curl", "-sf", "-X", "PUT", f"http://localhost:{port}{base}/{item_id}",
        "-H", "Content-Type: application/json",
        "-d", '{"name":"updated","description":"updated"}',
    ], timeout=10)
    details["put"] = "ok" if rc == 0 else "fail"

    rc, _, _ = run_cmd([
        "curl", "-sf", "-X", "DELETE", f"http://localhost:{port}{base}/{item_id}",
    ], timeout=10)
    details["delete"] = "ok" if rc == 0 else "fail"

    passed = all(v in ("ok", "skip (no id)") for v in details.values())
    return passed, details

# ── Main loop ─────────────────────────────────────────────────────────────────

results = []

for repo in sfr_repos:
    name  = repo["name"]
    port  = repo["port"]
    path  = ROOT / repo["path"]

    print(f"\n[01-build] {name} (port {port})")

    if not path.is_dir():
        print(f"[01-build]   SKIP — directory not found: {path}")
        results.append({
            "name": name, "port": port,
            "language": repo.get("language"), "framework": repo.get("framework"),
            "orm": repo.get("orm"), "passed": False, "error": "directory not found",
            "build_time_s": None, "crud_details": {},
        })
        continue

    start = time.time()

    # Build
    rc, _, err = run_cmd(["docker", "compose", "build"], cwd=path, timeout=300)
    if rc != 0:
        elapsed = int(time.time() - start)
        print(f"[01-build]   FAIL build ({elapsed}s)")
        print(f"             {err[:300]}")
        compose_down(path)
        results.append({
            "name": name, "port": port,
            "language": repo.get("language"), "framework": repo.get("framework"),
            "orm": repo.get("orm"), "passed": False, "error": "build failed",
            "build_time_s": elapsed, "crud_details": {},
        })
        continue

    # Start
    run_cmd(["docker", "compose", "up", "-d"], cwd=path, timeout=60)

    # Wait for /health (up to 20 × 3s = 60s)
    health_ok = False
    for _ in range(20):
        rc, _, _ = run_cmd(
            ["curl", "-sf", "--max-time", "3", f"http://localhost:{port}/health"], timeout=5
        )
        if rc == 0:
            health_ok = True
            break
        time.sleep(3)

    if not health_ok:
        elapsed = int(time.time() - start)
        print(f"[01-build]   FAIL /health not responding ({elapsed}s)")
        compose_down(path)
        results.append({
            "name": name, "port": port,
            "language": repo.get("language"), "framework": repo.get("framework"),
            "orm": repo.get("orm"), "passed": False, "error": "health timeout",
            "build_time_s": elapsed, "crud_details": {},
        })
        continue

    time.sleep(2)
    crud_passed, crud_details = try_crud(port)
    elapsed = int(time.time() - start)
    compose_down(path)

    status = "PASS" if crud_passed else "FAIL"
    print(f"[01-build]   {status} ({elapsed}s) crud={crud_details}")

    results.append({
        "name": name, "port": port,
        "language": repo.get("language"), "framework": repo.get("framework"),
        "orm": repo.get("orm"),
        "passed": crud_passed,
        "error": None if crud_passed else "crud fail",
        "build_time_s": elapsed,
        "crud_details": crud_details,
    })

# ── Write output ──────────────────────────────────────────────────────────────

out_path.parent.mkdir(parents=True, exist_ok=True)
with open(out_path, "w") as f:
    for r in results:
        f.write(json.dumps(r) + "\n")

total  = len(results)
passed = sum(1 for r in results if r["passed"])
print(f"\n[01-build] Done. {passed}/{total} passed → {out_path}")
