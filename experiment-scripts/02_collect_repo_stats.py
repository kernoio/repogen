#!/usr/bin/env python3
"""
Step 2 — Collect LOC and Docker image stats for SFR CRUD repos.

Uses repogen.core.collect_files to count source lines rather than shelling
out to find. Docker image size and layer counts are read from the Docker daemon.

Output: reproduced-experiments/results/crud-repo-stats.jsonl

Usage:
    python3 experiment-scripts/02_collect_repo_stats.py
    python3 experiment-scripts/02_collect_repo_stats.py --matrix scripts/crud-matrix.yaml
    python3 experiment-scripts/02_collect_repo_stats.py --out reproduced-experiments/results/crud-repo-stats.jsonl
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from repogen.core import collect_files, run_cmd

# ── CLI ───────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--matrix", default="scripts/crud-matrix.yaml")
parser.add_argument("--out", default="reproduced-experiments/results/crud-repo-stats.jsonl")
args = parser.parse_args()

matrix_path = ROOT / args.matrix if not Path(args.matrix).is_absolute() else Path(args.matrix)
out_path    = ROOT / args.out    if not Path(args.out).is_absolute()    else Path(args.out)

# ── Load matrix ───────────────────────────────────────────────────────────────

with open(matrix_path) as f:
    matrix = yaml.safe_load(f)

sfr_repos = [r for r in matrix["repos"]
             if r.get("port") and not r["name"].startswith("mono-")]

print(f"[02-stats] matrix: {matrix_path}")
print(f"[02-stats] repos:  {len(sfr_repos)}")
print(f"[02-stats] output: {out_path}")

# ── Source LOC counting ───────────────────────────────────────────────────────

SOURCE_EXTS = {".py", ".ts", ".js", ".go", ".rs", ".rb", ".java", ".kt", ".cs", ".cpp"}

def count_loc(repo_path: Path) -> tuple[int, int, str | None]:
    """Return (loc, file_count, src_dir_name) for the first source directory found."""
    for src_dir in ("src", "app", "lib"):
        d = repo_path / src_dir
        if not d.is_dir():
            continue
        files = collect_files(d)
        source_files = {k: v for k, v in files.items() if Path(k).suffix in SOURCE_EXTS}
        if not source_files:
            continue
        loc = sum(
            sum(1 for line in content.splitlines() if line.strip())
            for content in source_files.values()
        )
        return loc, len(source_files), src_dir
    return 0, 0, None

# ── Docker image stats ────────────────────────────────────────────────────────

def docker_image_stats(image_name: str) -> tuple[int | None, float | None]:
    """Return (layer_count, size_mb) for a Docker image. Returns (None, None) if not found."""
    # Size from docker images
    rc, out, _ = run_cmd(["docker", "images", "--format", "{{.Repository}} {{.Size}}"])
    size_mb = None
    if rc == 0:
        for line in out.strip().splitlines():
            if image_name in line:
                parts = line.split()
                size_str = parts[-1] if parts else ""
                try:
                    if "GB" in size_str:
                        size_mb = round(float(size_str.replace("GB", "")) * 1024, 1)
                    elif "MB" in size_str:
                        size_mb = round(float(size_str.replace("MB", "")), 1)
                    elif "kB" in size_str:
                        size_mb = round(float(size_str.replace("kB", "")) / 1024, 2)
                except ValueError:
                    pass
                break

    # Layer count from docker history
    rc, out, _ = run_cmd(["docker", "history", "-q", image_name])
    layers = None
    if rc == 0:
        layers = len([l for l in out.strip().splitlines() if l and l != "<missing>"])

    return layers, size_mb

# ── Main loop ─────────────────────────────────────────────────────────────────

results = []

for repo in sfr_repos:
    name = repo["name"]
    path = ROOT / repo["path"]
    print(f"[02-stats] {name}")

    if not path.is_dir():
        results.append({
            "name": name, "language": repo.get("language"),
            "framework": repo.get("framework"), "orm": repo.get("orm"),
            "loc": None, "files": None, "src_dir": None,
            "docker_layers": None, "image_size_mb": None,
        })
        continue

    loc, n_files, src_dir = count_loc(path)
    layers, size_mb = docker_image_stats(f"{name}-app")

    print(f"[02-stats]   loc={loc} files={n_files} src={src_dir} size={size_mb}MB layers={layers}")

    results.append({
        "name": name, "language": repo.get("language"),
        "framework": repo.get("framework"), "orm": repo.get("orm"),
        "loc": loc, "files": n_files, "src_dir": src_dir,
        "docker_layers": layers, "image_size_mb": size_mb,
    })

# ── Write output ──────────────────────────────────────────────────────────────

out_path.parent.mkdir(parents=True, exist_ok=True)
with open(out_path, "w") as f:
    for r in results:
        f.write(json.dumps(r) + "\n")

print(f"\n[02-stats] Done → {out_path}")
