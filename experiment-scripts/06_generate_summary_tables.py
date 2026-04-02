#!/usr/bin/env python3
"""
Step 6 — Aggregate all result files into summary tables (Markdown + LaTeX).

Reads from reproduced-experiments/results/ and writes:
  reproduced-experiments/results/summary.md
  reproduced-experiments/results/summary.tex

Usage:
    python3 experiment-scripts/06_generate_summary_tables.py
    python3 experiment-scripts/06_generate_summary_tables.py --results reproduced-experiments/results
    python3 experiment-scripts/06_generate_summary_tables.py --stars 3 4 5
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── CLI ───────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--results", default="reproduced-experiments/results",
                    help="Results directory (default: reproduced-experiments/results)")
parser.add_argument("--matrix", default="scripts/crud-matrix.yaml",
                    help="Path to crud-matrix.yaml (default: scripts/crud-matrix.yaml)")
parser.add_argument("--stars", nargs="+", type=int, default=[3, 4, 5],
                    help="Star thresholds for real-world results (default: 3 4 5)")
args = parser.parse_args()

results_dir = ROOT / args.results if not Path(args.results).is_absolute() else Path(args.results)
matrix_path = ROOT / args.matrix  if not Path(args.matrix).is_absolute()  else Path(args.matrix)

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]

def load_yaml(path: Path) -> dict | list:
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}

def pct(num: int, den: int) -> str:
    return f"{100 * num // den}%" if den else "—"

# ── Load results ──────────────────────────────────────────────────────────────

build    = load_jsonl(results_dir / "crud-build-metrics.jsonl")
stats    = load_jsonl(results_dir / "crud-repo-stats.jsonl")
pilot    = load_jsonl(results_dir / "crud-pilot-identification.jsonl")
gen_meth = load_yaml(results_dir  / "crud-generation-methods.yaml")

# Real-world results keyed by star threshold
real_verify: dict[int, list[dict]] = {}
real_sample: dict[int, dict]       = {}
for n in args.stars:
    real_verify[n] = load_jsonl(results_dir / f"real-verify-stars{n}.jsonl")
    real_sample[n] = load_yaml(results_dir  / f"real-repos-stars{n}.yaml")

matrix_data = load_yaml(matrix_path)

print(f"[06-summary] results dir: {results_dir}")
print(f"[06-summary] build:  {len(build)} rows")
print(f"[06-summary] stats:  {len(stats)} rows")
print(f"[06-summary] pilot:  {len(pilot)} rows")
for n in args.stars:
    print(f"[06-summary] real-verify-stars{n}: {len(real_verify[n])} rows")

# ── Markdown / LaTeX helpers ──────────────────────────────────────────────────

md_lines:  list[str] = []
tex_lines: list[str] = []

def md(line: str = ""):
    md_lines.append(line)

def tex(line: str = ""):
    tex_lines.append(line)

def md_section(title: str):
    md(f"\n## {title}\n")

def tex_section(title: str):
    tex(f"\n% --- {title} ---")

# ── 1. Dataset overview ───────────────────────────────────────────────────────

md_section("1. Dataset Overview")
tex_section("1. Dataset Overview")

if matrix_data:
    all_repos = matrix_data.get("repos", [])
    sfr_repos = [r for r in all_repos if r.get("port") and not r["name"].startswith("mono-")]
    mono_repos = [r for r in all_repos if r["name"].startswith("mono-")]

    langs: dict[str, int] = defaultdict(int)
    for r in sfr_repos:
        langs[r.get("language", "?")] += 1

    n_on_disk = sum(1 for r in sfr_repos if (ROOT / r["path"]).is_dir())

    md(f"- Total repos in matrix: **{len(all_repos)}**")
    md(f"  - SFR CRUD repos: {len(sfr_repos)}")
    md(f"  - Monorepos: {len(mono_repos)}")
    md(f"- Languages covered: {len(langs)} ({', '.join(sorted(langs.keys()))})")
    md(f"- SFR repos present on disk: {n_on_disk}/{len(sfr_repos)}")
else:
    md("_Matrix file not found._")

# ── 2. Build metrics ──────────────────────────────────────────────────────────

md_section("2. Build and Verification Metrics")
tex_section("2. Build Metrics")

if build:
    total  = len(build)
    passed = sum(1 for r in build if r["passed"])
    by_lang: dict[str, dict] = defaultdict(lambda: {"total": 0, "passed": 0, "times": []})

    for r in build:
        lang = r.get("language", "?")
        by_lang[lang]["total"] += 1
        if r["passed"]:
            by_lang[lang]["passed"] += 1
        if r.get("build_time_s") is not None:
            by_lang[lang]["times"].append(r["build_time_s"])

    md(f"\n**Overall: {passed}/{total} passed ({pct(passed, total)})**\n")
    md("| Language | Pass | Total | Pass Rate | Avg Build (s) |")
    md("|----------|------|-------|-----------|---------------|")
    for lang in sorted(by_lang):
        d   = by_lang[lang]
        avg = f"{sum(d['times']) // len(d['times'])}" if d["times"] else "—"
        md(f"| {lang} | {d['passed']} | {d['total']} | {pct(d['passed'], d['total'])} | {avg} |")

    md("\n**Per-repo detail:**\n")
    md("| Name | Language | Framework | ORM | Pass | Time (s) | CRUD details |")
    md("|------|----------|-----------|-----|------|----------|-------------|")
    for r in build:
        mark   = "✓" if r["passed"] else "✗"
        t      = str(r.get("build_time_s") or "—")
        err    = r.get("error") or ""
        crud   = str(r.get("crud_details") or err or "")
        md(f"| {r['name']} | {r.get('language','')} | {r.get('framework','')} | {r.get('orm','')} | {mark} | {t} | {crud} |")

    # LaTeX
    tex(r"\begin{table}[h]")
    tex(r"\centering")
    tex(r"\caption{Build verification results by language}")
    tex(r"\label{tab:build-results}")
    tex(r"\begin{tabular}{lrrrr}")
    tex(r"\toprule")
    tex(r"Language & Pass & Total & Pass Rate & Avg Build (s) \\")
    tex(r"\midrule")
    for lang in sorted(by_lang):
        d   = by_lang[lang]
        avg = f"{sum(d['times']) // len(d['times'])}" if d["times"] else "---"
        tex(f"{lang} & {d['passed']} & {d['total']} & {pct(d['passed'], d['total'])} & {avg} \\\\")
    tex(r"\midrule")
    tex(f"\\textbf{{Total}} & {passed} & {total} & {pct(passed, total)} & --- \\\\")
    tex(r"\bottomrule")
    tex(r"\end{tabular}")
    tex(r"\end{table}")
else:
    md("_Build metrics not yet collected (run Step 1)._")

# ── 3. Repo statistics ────────────────────────────────────────────────────────

md_section("3. Repository Statistics (LOC and Docker Image Size)")
tex_section("3. Repo Stats")

if stats:
    md("| Name | Language | Framework | ORM | LOC | Files | Layers | Size (MB) |")
    md("|------|----------|-----------|-----|-----|-------|--------|-----------|")
    for r in stats:
        layers = r.get("docker_layers") or "—"
        size   = r.get("image_size_mb") or "—"
        loc    = r.get("loc") or "—"
        files  = r.get("files") or "—"
        md(f"| {r['name']} | {r.get('language','')} | {r.get('framework','')} | {r.get('orm','')} | {loc} | {files} | {layers} | {size} |")

    locs = [r["loc"] for r in stats if r.get("loc")]
    if locs:
        md(f"\nLOC range: {min(locs)}–{max(locs)}, mean {sum(locs) // len(locs)}")
else:
    md("_Repo stats not yet collected (run Step 2)._")

# ── 4. Generation method ──────────────────────────────────────────────────────

md_section("4. Generation Method Classification")
tex_section("4. Generation Method")

if gen_meth:
    sfr_data  = gen_meth.get("sfr", {})
    mono_data = gen_meth.get("monorepo", {})
    summary   = gen_meth.get("summary", {})

    md(f"- SFR CRUD repos: **{summary.get('sfr_total', 0)}** total — "
       f"{summary.get('sfr_agent', 0)} agent-generated, "
       f"{summary.get('sfr_template', 0)} template-generated")
    md(f"- Monorepos: **{summary.get('monorepo_total', 0)}** — all agent-generated")
    if summary.get("note"):
        md(f"\n> {summary['note']}")

    # Cross-reference with build results
    build_by_name = {r["name"]: r for r in build}
    agent_names    = [n for n, v in sfr_data.items() if v.get("method") == "agent"]
    template_names = [n for n, v in sfr_data.items() if v.get("method") == "template"]

    a_pass = sum(1 for n in agent_names    if build_by_name.get(n, {}).get("passed"))
    t_pass = sum(1 for n in template_names if build_by_name.get(n, {}).get("passed"))
    a_tot  = sum(1 for n in agent_names    if n in build_by_name)
    t_tot  = sum(1 for n in template_names if n in build_by_name)

    if a_tot or t_tot:
        md("\n| Method | Count | Build Pass | Pass Rate |")
        md("|--------|-------|-----------|-----------|")
        if a_tot:
            md(f"| Agent    | {len(agent_names)}    | {a_pass}/{a_tot} | {pct(a_pass, a_tot)} |")
        if t_tot:
            md(f"| Template | {len(template_names)} | {t_pass}/{t_tot} | {pct(t_pass, t_tot)} |")
else:
    md("_Generation classification not yet run (run Step 3)._")

# ── 5. Pilot identification ───────────────────────────────────────────────────

md_section("5. Pilot Task: Technology Stack Identification")
tex_section("5. Pilot Task")

if pilot:
    n         = len(pilot)
    lang_acc  = sum(1 for r in pilot if r.get("lang_correct"))
    fw_acc    = sum(1 for r in pilot if r.get("fw_correct"))
    orm_acc   = sum(1 for r in pilot if r.get("orm_correct"))
    port_acc  = sum(1 for r in pilot if r.get("port_correct"))

    md(f"\n**{n} repos evaluated**\n")
    md("| Metric    | Correct | Total | Accuracy |")
    md("|-----------|---------|-------|----------|")
    md(f"| Language  | {lang_acc}  | {n} | {pct(lang_acc, n)}  |")
    md(f"| Framework | {fw_acc}    | {n} | {pct(fw_acc, n)}    |")
    md(f"| ORM       | {orm_acc}   | {n} | {pct(orm_acc, n)}   |")
    md(f"| Port      | {port_acc}  | {n} | {pct(port_acc, n)}  |")

    md("\n**Per-repo:**\n")
    md("| Name | GT Lang | Pred | GT FW | Pred | GT ORM | Pred | GT Port | Pred | L✓ | F✓ | O✓ | P✓ |")
    md("|------|---------|------|-------|------|--------|------|---------|------|----|----|----|----|")
    for r in pilot:
        marks = ("✓" if r.get("lang_correct") else "✗",
                 "✓" if r.get("fw_correct")   else "✗",
                 "✓" if r.get("orm_correct")  else "✗",
                 "✓" if r.get("port_correct") else "✗")
        md(
            f"| {r['name']} "
            f"| {r.get('gt_language','')} | {r.get('pred_language','')} "
            f"| {r.get('gt_framework','')} | {r.get('pred_framework','')} "
            f"| {r.get('gt_orm','')} | {r.get('pred_orm','')} "
            f"| {r.get('gt_port','')} | {r.get('pred_port','')} "
            f"| {marks[0]} | {marks[1]} | {marks[2]} | {marks[3]} |"
        )

    # LaTeX
    tex(r"\begin{table}[h]")
    tex(r"\centering")
    tex(r"\caption{Pilot task: technology stack identification accuracy}")
    tex(r"\label{tab:pilot}")
    tex(r"\begin{tabular}{lrr}")
    tex(r"\toprule")
    tex(r"Metric & Correct/Total & Accuracy (\%) \\")
    tex(r"\midrule")
    tex(f"Language  & {lang_acc}/{n}  & {pct(lang_acc, n).rstrip('%')} \\\\")
    tex(f"Framework & {fw_acc}/{n}    & {pct(fw_acc, n).rstrip('%')} \\\\")
    tex(f"ORM       & {orm_acc}/{n}   & {pct(orm_acc, n).rstrip('%')} \\\\")
    tex(f"Port      & {port_acc}/{n}  & {pct(port_acc, n).rstrip('%')} \\\\")
    tex(r"\bottomrule")
    tex(r"\end{tabular}")
    tex(r"\end{table}")
else:
    md("_Pilot identification not yet run (run Step 4)._")

# ── 6. Real-world comparison ──────────────────────────────────────────────────

md_section("6. Synthetic vs. Real-World Reproducibility")
tex_section("6. Real-World Comparison")

synth_total  = len(build)
synth_passed = sum(1 for r in build if r["passed"])

for n in args.stars:
    rdata = real_verify[n]
    if not rdata:
        md(f"_Real-world results (stars≥{n}) not yet collected (run Steps 5a+5b)._")
        continue

    rtotal    = len(rdata)
    rpassed   = sum(1 for r in rdata if r.get("passed"))
    has_dc    = sum(1 for r in rdata if r.get("has_compose"))
    responded = sum(1 for r in rdata if r.get("service_responded"))

    md(f"\n### Stars ≥ {n}\n")
    md("| Metric | Synthetic (ours) | Real-world sample |")
    md("|--------|-----------------|------------------|")
    md(f"| Repos evaluated              | {synth_total} | {rtotal} |")
    md(f"| Build + start success        | {synth_passed} ({pct(synth_passed, synth_total)}) | {rpassed} ({pct(rpassed, rtotal)}) |")
    md(f"| Has docker-compose           | {synth_total} (100%) | {has_dc} ({pct(has_dc, rtotal)}) |")
    md(f"| Service responded to a probe | {synth_passed} ({pct(synth_passed, synth_total)}) | {responded} ({pct(responded, rtotal)}) |")

    md("\n**Per real-world repo:**\n")
    md("| Repo | Language | Framework | Build OK | Responded | Path | Error |")
    md("|------|----------|-----------|----------|-----------|------|-------|")
    for r in rdata:
        build_ok = "✓" if r.get("passed") else "✗"
        resp_s   = "✓" if r.get("service_responded") else "✗"
        path_s   = r.get("responded_path") or "—"
        err      = r.get("error") or ""
        md(f"| {r['full_name']} | {r.get('language','')} | {r.get('framework','')} | {build_ok} | {resp_s} | {path_s} | {err} |")

# LaTeX table: all star thresholds combined
valid_ns = [n for n in args.stars if real_verify[n]]
if valid_ns and build:
    tex(r"\begin{table}[h]")
    tex(r"\centering")
    tex(r"\caption{Synthetic vs.\ real-world repository reproducibility by star threshold}")
    tex(r"\label{tab:real-world}")
    tex(r"\begin{tabular}{lcc" + "c" * len(valid_ns) + "}")
    tex(r"\toprule")
    tex("Metric & \\multicolumn{2}{c}{Synthetic} & " +
        " & ".join(f"Real (stars$\\geq${n})" for n in valid_ns) + r" \\")
    tex(r"\midrule")
    tex(f"Total repos & \\multicolumn{{2}}{{c}}{{{synth_total}}} & " +
        " & ".join(str(len(real_verify[n])) for n in valid_ns) + r" \\")
    tex(f"Build pass  & \\multicolumn{{2}}{{c}}{{{pct(synth_passed, synth_total)}}} & " +
        " & ".join(pct(sum(1 for r in real_verify[n] if r.get("passed")), len(real_verify[n]))
                   for n in valid_ns) + r" \\")
    tex(f"Has compose & \\multicolumn{{2}}{{c}}{{100\\%}} & " +
        " & ".join(pct(sum(1 for r in real_verify[n] if r.get("has_compose")), len(real_verify[n]))
                   for n in valid_ns) + r" \\")
    tex(r"\bottomrule")
    tex(r"\end{tabular}")
    tex(r"\end{table}")

# ── Write outputs ─────────────────────────────────────────────────────────────

now     = datetime.now().strftime("%Y-%m-%d %H:%M")
md_out  = results_dir / "summary.md"
tex_out = results_dir / "summary.tex"

results_dir.mkdir(parents=True, exist_ok=True)

md_header = f"# Experiment Results Summary\n\nGenerated: {now}\n"
with open(md_out, "w") as f:
    f.write(md_header + "\n".join(md_lines) + "\n")

tex_header = (
    "% Experiment Results Summary\n"
    f"% Generated: {now}\n"
    "% Paste individual tables into paper as needed.\n"
)
with open(tex_out, "w") as f:
    f.write(tex_header + "\n".join(tex_lines) + "\n")

print(f"\n[06-summary] Markdown → {md_out}")
print(f"[06-summary] LaTeX   → {tex_out}")
