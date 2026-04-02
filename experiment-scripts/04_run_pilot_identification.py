#!/usr/bin/env python3
"""
Step 4 — Pilot task: Claude identifies language, framework, ORM, database, and
port from CRUD repo structure.

Model: claude-haiku-4-5-20251001  (intentionally cheap/fast; this is the same
model used in the original experiments).

Uses repogen.core.collect_files for file tree construction.

Output: reproduced-experiments/results/crud-pilot-identification.jsonl

Usage:
    python3 experiment-scripts/04_run_pilot_identification.py
    python3 experiment-scripts/04_run_pilot_identification.py --matrix scripts/crud-matrix.yaml
    python3 experiment-scripts/04_run_pilot_identification.py --model claude-haiku-4-5-20251001
"""

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Load .env before importing anthropic
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    env_f = ROOT / ".env"
    if env_f.exists():
        for line in env_f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

from repogen.core import collect_files, SKIP_DIRS

# ── CLI ───────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--matrix", default="scripts/crud-matrix.yaml")
parser.add_argument("--out", default="reproduced-experiments/results/crud-pilot-identification.jsonl")
parser.add_argument("--model", default="claude-haiku-4-5-20251001",
                    help="Claude model to use for identification (default: claude-haiku-4-5-20251001)")
args = parser.parse_args()

matrix_path = ROOT / args.matrix if not Path(args.matrix).is_absolute() else Path(args.matrix)
out_path    = ROOT / args.out    if not Path(args.out).is_absolute()    else Path(args.out)

# ── API key ───────────────────────────────────────────────────────────────────

api_key = os.environ.get("ANTHROPIC_API_KEY")
if not api_key:
    print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
    sys.exit(1)

try:
    import anthropic
except ImportError:
    print("ERROR: pip install anthropic", file=sys.stderr)
    sys.exit(1)

client = anthropic.Anthropic(api_key=api_key)

# ── Load matrix ───────────────────────────────────────────────────────────────

with open(matrix_path) as f:
    matrix = yaml.safe_load(f)

sfr_repos = [r for r in matrix["repos"]
             if r.get("port") and not r["name"].startswith("mono-")]

print(f"[04-pilot] matrix: {matrix_path}")
print(f"[04-pilot] repos:  {len(sfr_repos)}")
print(f"[04-pilot] model:  {args.model}")
print(f"[04-pilot] output: {out_path}")

# ── Context builders ──────────────────────────────────────────────────────────

MAX_SRC     = 3000
MAX_COMPOSE = 1500
MAX_TREE    = 60

def file_tree(repo_path: Path) -> str:
    lines: list[str] = []
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        rel = Path(root).relative_to(repo_path)
        depth = len(rel.parts)
        indent = "  " * depth
        if rel != Path("."):
            lines.append(f"{indent}{rel.name}/")
        for fn in sorted(files)[:20]:
            lines.append(f"  {indent}{fn}")
        if len(lines) >= MAX_TREE:
            break
    return "\n".join(lines[:MAX_TREE])


def main_source(repo_path: Path) -> str:
    candidates = [
        "main.py", "app.py", "server.py",
        "main.ts", "index.ts",
        "main.go",
        "main.rs",
        "main.rb",
        "Application.java", "Application.kt",
        "Program.cs",
        "main.cpp",
    ]
    for src_dir in ("src", "app", "."):
        d = repo_path / src_dir
        for fn in candidates:
            fp = d / fn
            if fp.exists():
                try:
                    return fp.read_text(errors="ignore")[:MAX_SRC]
                except OSError:
                    pass
    return ""


def compose_snippet(repo_path: Path) -> str:
    for fn in ("docker-compose.yml", "docker-compose.yaml"):
        fp = repo_path / fn
        if fp.exists():
            try:
                return fp.read_text(errors="ignore")[:MAX_COMPOSE]
            except OSError:
                pass
    return ""


PROMPT_TEMPLATE = """\
You are analysing a software repository to identify its technology stack.

File tree:
```
{tree}
```

Main source file:
```
{source}
```

docker-compose.yml (excerpt):
```yaml
{compose}
```

Answer in JSON with exactly these keys:
{{
  "language": "<language name, lowercase>",
  "framework": "<framework name, lowercase>",
  "orm": "<ORM or database library name, lowercase, or 'none'>",
  "database": "<database technology, lowercase, e.g. postgresql, mysql, mongodb, or 'none'>",
  "port": <integer port number exposed by the app container>
}}
Respond with JSON only, no explanation."""

# ── Main loop ─────────────────────────────────────────────────────────────────

results = []

for i, repo in enumerate(sfr_repos):
    name    = repo["name"]
    path    = ROOT / repo["path"]
    gt_lang = repo.get("language", "")
    gt_fw   = repo.get("framework", "")
    gt_orm  = repo.get("orm", "")
    gt_port = repo.get("port", 0)

    if not path.is_dir():
        print(f"[04-pilot] ({i+1}/{len(sfr_repos)}) SKIP {name} — directory not found")
        continue

    print(f"[04-pilot] ({i+1}/{len(sfr_repos)}) Querying {args.model} for {name}...")

    prompt = PROMPT_TEMPLATE.format(
        tree    = file_tree(path),
        source  = main_source(path),
        compose = compose_snippet(path),
    )

    try:
        msg = client.messages.create(
            model=args.model,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
            raw = raw.split("```")[0].strip()
        pred = json.loads(raw)
    except Exception as e:
        print(f"[04-pilot]   ERROR: {e}")
        continue

    lang_ok = pred.get("language", "").lower() == gt_lang.lower()
    fw_ok   = pred.get("framework", "").lower() == gt_fw.lower()
    port_ok = pred.get("port") == gt_port
    # Normalise ORM names for comparison (remove hyphens/underscores)
    orm_ok  = (
        pred.get("orm", "").lower().replace("-", "").replace("_", "") ==
        gt_orm.lower().replace("-", "").replace("_", "")
    )

    result = {
        "name": name,
        "gt_language":  gt_lang,  "pred_language":  pred.get("language", ""),
        "gt_framework":  gt_fw,   "pred_framework":  pred.get("framework", ""),
        "gt_orm":        gt_orm,  "pred_orm":        pred.get("orm", ""),
        "gt_port":       gt_port, "pred_port":       pred.get("port"),
        "pred_database": pred.get("database", ""),
        "lang_correct":  lang_ok,
        "fw_correct":    fw_ok,
        "orm_correct":   orm_ok,
        "port_correct":  port_ok,
    }
    results.append(result)

    marks = (
        "✓" if lang_ok else "✗",
        "✓" if fw_ok   else "✗",
        "✓" if orm_ok  else "✗",
        "✓" if port_ok else "✗",
    )
    print(
        f"[04-pilot]   "
        f"lang={marks[0]}({pred.get('language')}) "
        f"fw={marks[1]}({pred.get('framework')}) "
        f"orm={marks[2]}({pred.get('orm')}) "
        f"port={marks[3]}({pred.get('port')})"
    )

# ── Write output ──────────────────────────────────────────────────────────────

out_path.parent.mkdir(parents=True, exist_ok=True)
with open(out_path, "w") as f:
    for r in results:
        f.write(json.dumps(r) + "\n")

n = len(results)
if n:
    print(f"\n[04-pilot] Accuracy ({n} repos):")
    for label, key in [
        ("Language",  "lang_correct"),
        ("Framework", "fw_correct"),
        ("ORM",       "orm_correct"),
        ("Port",      "port_correct"),
    ]:
        acc = sum(1 for r in results if r[key]) / n * 100
        print(f"[04-pilot]   {label:<12} {acc:.1f}%")

print(f"[04-pilot] Output: {out_path}")
