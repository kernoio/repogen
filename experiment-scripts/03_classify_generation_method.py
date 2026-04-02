#!/usr/bin/env python3
"""
Step 3 — Classify each repo as template-generated or agent-generated.

For SFR CRUD repos: all are agent-generated (no CRUD templates exist).
For monorepos: all are agent-generated (assembled from SFR service directories).

Output: reproduced-experiments/results/crud-generation-methods.yaml

Usage:
    python3 experiment-scripts/03_classify_generation_method.py
    python3 experiment-scripts/03_classify_generation_method.py --matrix scripts/crud-matrix.yaml
"""

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── CLI ───────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--matrix", default="scripts/crud-matrix.yaml")
parser.add_argument("--out", default="reproduced-experiments/results/crud-generation-methods.yaml")
args = parser.parse_args()

matrix_path = ROOT / args.matrix if not Path(args.matrix).is_absolute() else Path(args.matrix)
out_path    = ROOT / args.out    if not Path(args.out).is_absolute()    else Path(args.out)

# ── Load matrix ───────────────────────────────────────────────────────────────

with open(matrix_path) as f:
    matrix = yaml.safe_load(f)

sfr_repos  = [r for r in matrix["repos"] if r.get("port") and not r["name"].startswith("mono-")]
mono_repos = [r for r in matrix["repos"] if r["name"].startswith("mono-")]

print(f"[03-classify] matrix: {matrix_path}")
print(f"[03-classify] SFR: {len(sfr_repos)}  monorepos: {len(mono_repos)}")

# ── Classify ──────────────────────────────────────────────────────────────────

results: dict = {"sfr": {}, "monorepo": {}, "summary": {}}

for repo in sfr_repos:
    name   = repo["name"]
    exists = (ROOT / repo["path"]).is_dir()
    results["sfr"][name] = {
        "method":    "agent",
        "reason":    "no CRUD templates — all SFR CRUD repos are agent-generated",
        "exists":    exists,
        "language":  repo.get("language"),
        "framework": repo.get("framework"),
        "orm":       repo.get("orm"),
    }
    print(f"[03-classify]   {name}: agent (exists={exists})")

for repo in mono_repos:
    name   = repo["name"]
    exists = (ROOT / repo["path"]).is_dir()
    results["monorepo"][name] = {
        "method":  "agent",
        "reason":  "monorepo — assembled from SFR CRUD service directories",
        "exists":  exists,
    }
    print(f"[03-classify]   {name}: agent/composite (exists={exists})")

n_sfr  = len(sfr_repos)
n_mono = len(mono_repos)
results["summary"] = {
    "sfr_total":       n_sfr,
    "sfr_agent":       n_sfr,
    "sfr_template":    0,
    "monorepo_total":  n_mono,
    "monorepo_agent":  n_mono,
    "note": (
        "All CRUD repos are agent-generated. Unlike health-check SFR repos "
        "(which have Jinja2 templates for many stacks), no templates exist for "
        "CRUD repos due to the higher complexity of ORM integration, "
        "database migrations, and multi-service orchestration."
    ),
}

# ── Write output ──────────────────────────────────────────────────────────────

out_path.parent.mkdir(parents=True, exist_ok=True)
with open(out_path, "w") as f:
    yaml.dump(results, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

print(f"\n[03-classify] Done. SFR: {n_sfr} agent, 0 template → {out_path}")
