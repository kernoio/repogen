#!/usr/bin/env python3
"""
coverage.py — Compute language/framework/size coverage for the generated dataset.

Reads matrix.yaml (or progress.yaml) and writes a gap report to gaps.md.

Usage:
  python scripts/coverage.py                    # print coverage summary
  python scripts/coverage.py --report gaps.md   # write gap report to file
  python scripts/coverage.py --verified-only    # only count verified repos
"""

import argparse
import itertools
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("Error: PyYAML required. Install with: pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent
MATRIX_PATH = ROOT / "matrix.yaml"
PROGRESS_PATH = ROOT / "progress.yaml"
LANGUAGES_PATH = ROOT / "languages.yaml"


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def compute_coverage(verified_only: bool = False) -> dict:
    matrix = load_yaml(MATRIX_PATH)
    progress = load_yaml(PROGRESS_PATH)
    langs_config = load_yaml(LANGUAGES_PATH)

    repos = matrix.get("repos", [])
    prog_repos = progress.get("repos", {})

    if verified_only:
        repos = [
            r for r in repos
            if prog_repos.get(r["name"], {}).get("verified", False)
        ]

    # Collect unique languages and frameworks that appear in any repo
    seen_languages: set = set()
    seen_frameworks: set = set()
    lang_counts: dict = {}
    framework_counts: dict = {}
    size_counts: dict = {}
    lang_pairs_covered: set = set()
    framework_pairs_covered: set = set()

    for repo in repos:
        languages = repo.get("languages", [repo.get("language")])
        languages = [l for l in languages if l]
        frameworks = repo.get("frameworks", [repo.get("framework")])
        frameworks = [f for f in frameworks if f]

        for lang in languages:
            seen_languages.add(lang)
            lang_counts[lang] = lang_counts.get(lang, 0) + 1

        for fw in frameworks:
            seen_frameworks.add(fw)
            framework_counts[fw] = framework_counts.get(fw, 0) + 1

        size = len(languages)
        size_counts[size] = size_counts.get(size, 0) + 1

        # Language pairs
        for pair in itertools.combinations(sorted(languages), 2):
            lang_pairs_covered.add(pair)

        # Framework pairs
        for pair in itertools.combinations(sorted(frameworks), 2):
            framework_pairs_covered.add(pair)

    # All languages from languages.yaml
    all_languages = sorted(langs_config.get("languages", {}).keys())
    all_frameworks = []
    for lang, lang_data in langs_config.get("languages", {}).items():
        for fw in lang_data.get("frameworks", {}).keys():
            all_frameworks.append(f"{lang}/{fw}")
    all_frameworks = sorted(all_frameworks)

    # All possible language pairs
    all_lang_pairs = set(itertools.combinations(sorted(all_languages), 2))
    all_fw_pairs = set(itertools.combinations(sorted(all_frameworks), 2))

    missing_languages = sorted(set(all_languages) - seen_languages)
    missing_lang_pairs = sorted(all_lang_pairs - lang_pairs_covered)
    missing_fw_pairs = sorted(all_fw_pairs - framework_pairs_covered)

    max_size = max(size_counts.keys()) if size_counts else 0
    all_sizes = set(range(2, max_size + 1)) if max_size > 1 else set()
    covered_sizes = set(k for k in size_counts if k >= 2)
    missing_sizes = sorted(all_sizes - covered_sizes)

    return {
        "total_repos": len(repos),
        "languages_covered": sorted(seen_languages),
        "languages_missing": missing_languages,
        "frameworks_covered": sorted(seen_frameworks),
        "lang_counts": lang_counts,
        "framework_counts": framework_counts,
        "size_counts": dict(sorted(size_counts.items())),
        "missing_sizes": missing_sizes,
        "lang_pairs_covered": len(lang_pairs_covered),
        "lang_pairs_total": len(all_lang_pairs),
        "lang_pairs_missing": missing_lang_pairs,
        "fw_pairs_covered": len(framework_pairs_covered),
        "fw_pairs_total": len(all_fw_pairs),
        "fw_pairs_missing": missing_fw_pairs[:20],  # cap for readability
        "fw_pairs_missing_count": len(missing_fw_pairs),
    }


def format_report(cov: dict) -> str:
    lines = ["# Coverage Report\n"]

    lines.append(f"Total repos: **{cov['total_repos']}**\n")

    # Language coverage
    lines.append("## Language coverage\n")
    covered = cov["languages_covered"]
    missing = cov["languages_missing"]
    lines.append(f"- Covered ({len(covered)}): {', '.join(covered) or 'none'}")
    lines.append(f"- Missing ({len(missing)}): {', '.join(missing) or 'none'}\n")

    # Language appearances
    lines.append("### Appearances per language\n")
    lines.append("| Language | Repo count |")
    lines.append("|----------|:----------:|")
    for lang, count in sorted(cov["lang_counts"].items()):
        lines.append(f"| {lang} | {count} |")
    lines.append("")

    # Size distribution
    lines.append("## Size coverage (languages per repo)\n")
    lines.append("| Size | Count |")
    lines.append("|:----:|:-----:|")
    for size, count in cov["size_counts"].items():
        lines.append(f"| {size} | {count} |")
    if cov["missing_sizes"]:
        missing_str = ", ".join(str(s) for s in cov["missing_sizes"])
        lines.append(f"\nMissing sizes: **{missing_str}**\n")
    else:
        lines.append("\nAll sizes covered.\n")

    # Language pair coverage
    lp = cov["lang_pairs_covered"]
    lt = cov["lang_pairs_total"]
    lines.append(f"## Language pair coverage\n\n{lp}/{lt} pairs covered.\n")
    if cov["lang_pairs_missing"]:
        lines.append("### Missing language pairs\n")
        for a, b in cov["lang_pairs_missing"]:
            lines.append(f"- {a} + {b}")
        lines.append("")

    # Framework pair coverage
    fp = cov["fw_pairs_covered"]
    ft = cov["fw_pairs_total"]
    lines.append(f"## Framework pair coverage\n\n{fp}/{ft} pairs covered.\n")
    if cov["fw_pairs_missing_count"] > 0:
        lines.append(f"Missing: {cov['fw_pairs_missing_count']} pairs (showing first 20)\n")
        for a, b in cov["fw_pairs_missing"]:
            lines.append(f"- {a} + {b}")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute dataset coverage and gaps")
    parser.add_argument("--report", metavar="FILE", help="Write gap report to file (default: stdout)")
    parser.add_argument("--verified-only", action="store_true", help="Only count verified repos")
    args = parser.parse_args()

    cov = compute_coverage(verified_only=args.verified_only)
    report = format_report(cov)

    if args.report:
        out = Path(args.report)
        out.write_text(report)
        print(f"Coverage report written to {out}")
        # Print summary to stdout too
        print(f"\nSummary:")
        print(f"  Repos: {cov['total_repos']}")
        print(f"  Languages: {len(cov['languages_covered'])}/{len(cov['languages_covered']) + len(cov['languages_missing'])}")
        print(f"  Language pairs: {cov['lang_pairs_covered']}/{cov['lang_pairs_total']}")
        print(f"  Framework pairs: {cov['fw_pairs_covered']}/{cov['fw_pairs_total']}")
        if cov["missing_sizes"]:
            print(f"  Missing sizes: {cov['missing_sizes']}")
    else:
        print(report)


if __name__ == "__main__":
    main()
