#!/usr/bin/env python3
"""
Step 5a — Sample real-world REST API repos from GitHub.

Uses framework + ORM-signal keywords (not "crud" which returns 0 results on
GitHub search). The verification step (05b) checks for CRUD-style endpoints.

Output: reproduced-experiments/results/real-repos-stars<N>.yaml

Usage:
    python3 experiment-scripts/05a_sample_real_repos.py --min-stars 5
    python3 experiment-scripts/05a_sample_real_repos.py --min-stars 3 --want 5
    python3 experiment-scripts/05a_sample_real_repos.py --min-stars 5 \
        --out reproduced-experiments/results/real-repos-stars5.yaml
"""

import argparse
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Load .env before importing requests
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

try:
    import requests
except ImportError:
    print("ERROR: pip install requests", file=sys.stderr)
    sys.exit(1)

# ── CLI ───────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--min-stars", type=int, default=5,
                    help="Minimum GitHub stars (default: 5)")
parser.add_argument("--years",     type=int, default=5,
                    help="Only repos pushed within this many years (default: 5)")
parser.add_argument("--want",      type=int, default=5,
                    help="Target repos per stack (default: 5)")
parser.add_argument("--out", default=None,
                    help="Output YAML path (default: reproduced-experiments/results/real-repos-stars<N>.yaml)")
args = parser.parse_args()

if args.out is None:
    args.out = f"reproduced-experiments/results/real-repos-stars{args.min_stars}.yaml"

out_path = ROOT / args.out if not Path(args.out).is_absolute() else Path(args.out)

# ── GitHub token ──────────────────────────────────────────────────────────────

token = os.environ.get("GITHUB_TOKEN")
if not token:
    print("ERROR: GITHUB_TOKEN not set", file=sys.stderr)
    sys.exit(1)

HEADERS = {
    "Authorization": f"token {token}",
    "Accept": "application/vnd.github.v3+json",
}

# ── Search targets ────────────────────────────────────────────────────────────
# (our_lang, our_fw, our_orm, github_lang, search_keywords, want_override)
# want_override=None means use --want; an int overrides for rarer stacks.

SEARCH_TARGETS = [
    ("python",     "fastapi",  "sqlalchemy",       "Python",     "fastapi sqlalchemy dockerfile",        None),
    ("python",     "flask",    "flask-sqlalchemy",  "Python",     "flask sqlalchemy dockerfile",          None),
    ("python",     "django",   "django-orm",        "Python",     "django rest framework dockerfile",     None),
    ("typescript", "express",  "prisma",            "TypeScript", "express prisma dockerfile",            None),
    ("typescript", "nestjs",   "typeorm",           "TypeScript", "nestjs typeorm dockerfile",            None),
    ("javascript", "express",  "prisma",            "JavaScript", "express prisma dockerfile",            None),
    ("kotlin",     "ktor",     "exposed",           "Kotlin",     "ktor dockerfile",                     3),
    ("go",         "gin",      "gorm",              "Go",         "gin gorm dockerfile",                 3),
    ("rust",       "axum",     "sqlx",              "Rust",       "axum sqlx dockerfile",                3),
    ("java",       "spring",   "spring-data-jpa",   "Java",       "spring boot jpa dockerfile",          3),
    ("ruby",       "rails",    "activerecord",      "Ruby",       "rails postgresql dockerfile",         3),
    ("csharp",     "aspnet",   "efcore",            "C#",         "aspnet efcore dockerfile",            3),
    ("cpp",        "crow",     "libpqxx",           "C++",        "crow rest dockerfile",                2),
]

# ── Search ────────────────────────────────────────────────────────────────────

cutoff = (datetime.now() - timedelta(days=365 * args.years)).strftime("%Y-%m-%d")
print(f"[05a-sample] min_stars={args.min_stars}  years={args.years}  cutoff={cutoff}")
print(f"[05a-sample] output: {out_path}")


def search_repos(gh_lang: str, keywords: str, count: int) -> list[dict]:
    query = (
        f"language:{gh_lang} {keywords} "
        f"pushed:>{cutoff} stars:>={args.min_stars}"
    )
    params = {
        "q":        query,
        "sort":     "updated",
        "order":    "desc",
        "per_page": min(count * 4, 40),
    }
    try:
        resp = requests.get(
            "https://api.github.com/search/repositories",
            headers=HEADERS,
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("items", [])
    except Exception as exc:
        print(f"  WARNING: {exc}")
        return []


# ── Main loop ─────────────────────────────────────────────────────────────────

results: dict = {}
sampled_at = datetime.now().strftime("%Y-%m-%d")

for our_lang, our_fw, our_orm, gh_lang, keywords, want_override in SEARCH_TARGETS:
    wanted = want_override if want_override is not None else args.want
    print(f"[05a-sample] {gh_lang} '{keywords}' (want {wanted})...")

    items = search_repos(gh_lang, keywords, wanted)
    bucket: list[dict] = []

    for item in items:
        if len(bucket) >= wanted:
            break
        if item.get("archived") or item.get("fork"):
            continue
        bucket.append({
            "full_name":      item["full_name"],
            "clone_url":      item["clone_url"],
            "html_url":       item["html_url"],
            "stars":          item.get("stargazers_count", 0),
            "pushed_at":      item.get("pushed_at", ""),
            "default_branch": item.get("default_branch", "main"),
            "description":    item.get("description", ""),
        })

    key = f"{our_lang}-{our_fw}"
    results[key] = {
        "language":   our_lang,
        "framework":  our_fw,
        "orm":        our_orm,
        "repos":      bucket,
        "sampled_at": sampled_at,
    }
    print(f"[05a-sample]   Found {len(bucket)} repos")
    time.sleep(1)  # respect GitHub rate limits

# ── Write output ──────────────────────────────────────────────────────────────

total = sum(len(v["repos"]) for v in results.values())
out_path.parent.mkdir(parents=True, exist_ok=True)
with open(out_path, "w") as f:
    yaml.dump(results, f, default_flow_style=False, sort_keys=True, allow_unicode=True)

print(f"\n[05a-sample] Done. {total} repos → {out_path}")
