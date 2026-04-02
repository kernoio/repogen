#!/usr/bin/env python3
"""
Step 5b — Clone and verify sampled real-world CRUD repos.

Clones each repo (shallow), runs docker compose build + up, then probes a set
of common REST endpoint paths. "Passed" = service started and responded to at
least one probe path.

Uses repogen.core.run_cmd and compose_down for subprocess management.

Output: reproduced-experiments/results/real-verify-stars<N>.jsonl

Usage:
    python3 experiment-scripts/05b_verify_real_repos.py \
        --sample reproduced-experiments/results/real-repos-stars5.yaml \
        --out    reproduced-experiments/results/real-verify-stars5.jsonl \
        --clonedir /tmp/eval-crud-repos

    # Run all three star thresholds
    for N in 3 4 5; do
      python3 experiment-scripts/05b_verify_real_repos.py \
          --sample reproduced-experiments/results/real-repos-stars${N}.yaml \
          --out    reproduced-experiments/results/real-verify-stars${N}.jsonl \
          --clonedir /tmp/eval-crud-repos
    done
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from repogen.core import run_cmd, compose_down

# ── CLI ───────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--sample",   required=True,
                    help="YAML sample file from 05a (e.g. reproduced-experiments/results/real-repos-stars5.yaml)")
parser.add_argument("--out",      required=True,
                    help="Output JSONL path")
parser.add_argument("--clonedir", required=True,
                    help="Directory to clone repos into (reused across runs)")
args = parser.parse_args()

sample_path = ROOT / args.sample   if not Path(args.sample).is_absolute()   else Path(args.sample)
out_path    = ROOT / args.out      if not Path(args.out).is_absolute()       else Path(args.out)
clone_base  = Path(args.clonedir)

clone_base.mkdir(parents=True, exist_ok=True)
out_path.parent.mkdir(parents=True, exist_ok=True)

print(f"[05b-verify] sample:   {sample_path}")
print(f"[05b-verify] output:   {out_path}")
print(f"[05b-verify] clonedir: {clone_base}")

# ── REST probe paths ──────────────────────────────────────────────────────────
# Ordered by likelihood of being the "items" resource in a CRUD repo.

REST_PATHS = [
    "/items", "/api/items", "/api/v1/items",
    "/users", "/api/users", "/api/v1/users",
    "/products", "/api/products",
    "/todos", "/api/todos",
    "/health", "/api/health",
    "/",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def detect_port(compose_f: Path) -> int:
    """Extract first non-DB host port from docker-compose.yml."""
    DB_PORTS = {5432, 3306, 27017, 6379, 5672, 9092, 2181}
    try:
        content = compose_f.read_text(errors="ignore")
        for m in re.finditer(r'["\']?(\d+):(\d+)["\']?', content):
            host_port = int(m.group(1))
            cont_port = int(m.group(2))
            if cont_port not in DB_PORTS:
                return host_port
    except Exception:
        pass
    return 9999


def probe_service(port: int) -> tuple[bool, str | None, int | None]:
    """Try REST_PATHS; return (responded, path, http_code)."""
    for path in REST_PATHS:
        rc, out, _ = run_cmd(
            ["curl", "-sf", "-o", "/dev/null", "-w", "%{http_code}",
             "--max-time", "5", f"http://localhost:{port}{path}"],
            timeout=8,
        )
        code_str = out.strip()
        if rc == 0 and code_str and code_str not in ("000", ""):
            try:
                return True, path, int(code_str)
            except ValueError:
                pass
        time.sleep(0.2)
    return False, None, None


# ── Load sample ───────────────────────────────────────────────────────────────

with open(sample_path) as f:
    data = yaml.safe_load(f)

# ── Main loop ─────────────────────────────────────────────────────────────────

results: list[dict] = []

for key, bucket in data.items():
    language  = bucket["language"]
    framework = bucket["framework"]
    orm       = bucket.get("orm", "")

    for repo_info in bucket.get("repos", []):
        full_name = repo_info["full_name"]
        clone_url = repo_info["clone_url"]
        safe_name = full_name.replace("/", "__")
        clone_dir = clone_base / safe_name

        print(f"\n[05b-verify] {full_name} ({language}/{framework})")

        # ── Clone ─────────────────────────────────────────────────────────────
        if not clone_dir.is_dir():
            print(f"[05b-verify]   Cloning...")
            rc, _, err = run_cmd(
                ["git", "clone", "--depth", "1", clone_url, str(clone_dir)],
                timeout=120,
            )
            if rc != 0:
                print(f"[05b-verify]   FAIL clone: {err[:200]}")
                results.append({
                    "full_name": full_name, "language": language,
                    "framework": framework, "orm": orm,
                    "stars": repo_info.get("stars", 0),
                    "passed": False, "build_time_s": None,
                    "has_dockerfile": False, "has_compose": False,
                    "service_responded": False, "responded_path": None,
                    "http_code": None, "error": "clone failed",
                })
                continue
        else:
            print(f"[05b-verify]   Already cloned.")

        has_dockerfile = (clone_dir / "Dockerfile").exists()
        compose_yml  = clone_dir / "docker-compose.yml"
        compose_yaml = clone_dir / "docker-compose.yaml"
        has_compose  = compose_yml.exists() or compose_yaml.exists()

        if not has_compose:
            print(f"[05b-verify]   SKIP — no docker-compose.yml")
            results.append({
                "full_name": full_name, "language": language,
                "framework": framework, "orm": orm,
                "stars": repo_info.get("stars", 0),
                "passed": False, "build_time_s": None,
                "has_dockerfile": has_dockerfile, "has_compose": False,
                "service_responded": False, "responded_path": None,
                "http_code": None, "error": "no docker-compose.yml",
            })
            continue

        compose_f = compose_yml if compose_yml.exists() else compose_yaml
        port = detect_port(compose_f)

        start = time.time()

        # ── Build ─────────────────────────────────────────────────────────────
        rc, _, err = run_cmd(["docker", "compose", "build"], cwd=clone_dir, timeout=300)
        if rc != 0:
            elapsed = int(time.time() - start)
            print(f"[05b-verify]   FAIL build ({elapsed}s)")
            compose_down(clone_dir)
            results.append({
                "full_name": full_name, "language": language,
                "framework": framework, "orm": orm,
                "stars": repo_info.get("stars", 0),
                "passed": False, "build_time_s": elapsed,
                "has_dockerfile": has_dockerfile, "has_compose": True,
                "service_responded": False, "responded_path": None,
                "http_code": None, "error": "build failed",
            })
            continue

        # ── Start ─────────────────────────────────────────────────────────────
        run_cmd(["docker", "compose", "up", "-d"], cwd=clone_dir, timeout=60)

        # ── Wait and probe (up to ~30s total) ─────────────────────────────────
        responded = False
        resp_path = None
        resp_code = None
        for wait in [3, 3, 3, 5, 5, 5, 6]:
            time.sleep(wait)
            responded, resp_path, resp_code = probe_service(port)
            if responded:
                break

        elapsed = int(time.time() - start)
        compose_down(clone_dir)

        passed = responded
        status = "PASS" if passed else "FAIL"
        print(f"[05b-verify]   {status} ({elapsed}s) port={port} path={resp_path} code={resp_code}")

        results.append({
            "full_name": full_name, "language": language,
            "framework": framework, "orm": orm,
            "stars": repo_info.get("stars", 0),
            "passed": passed, "build_time_s": elapsed,
            "has_dockerfile": has_dockerfile, "has_compose": True,
            "service_responded": responded,
            "responded_path": resp_path, "http_code": resp_code,
            "error": None,
        })

# ── Write output ──────────────────────────────────────────────────────────────

with open(out_path, "w") as f:
    for r in results:
        f.write(json.dumps(r) + "\n")

total  = len(results)
passed = sum(1 for r in results if r["passed"])
print(f"\n[05b-verify] Done. {passed}/{total} passed → {out_path}")
