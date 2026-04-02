# Experiment Scripts

Reproducible pipeline for the experiments described in the accompanying paper.
Each script is a numbered step that reads from `scripts/crud-matrix.yaml` and
writes results to `reproduced-experiments/results/`.

All scripts import from the `repogen` package — run them from the repo root
after installing dependencies:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

Set the required environment variables in `.env` (see `env.example`):

```
ANTHROPIC_API_KEY=sk-ant-...   # required by steps 04 and 06 (Claude API)
GITHUB_TOKEN=ghp_...           # required by step 05a (GitHub API)
```

---

## Pipeline overview

```
01  Build & CRUD-test all synthetic repos      → crud-build-metrics.jsonl
02  Collect LOC + Docker image stats           → crud-repo-stats.jsonl
03  Classify generation method (agent/template)→ crud-generation-methods.yaml
04  Pilot: Claude identifies tech stack        → crud-pilot-identification.jsonl
05a Sample real-world repos from GitHub        → real-repos-stars{N}.yaml
05b Clone + verify sampled repos               → real-verify-stars{N}.jsonl
06  Aggregate results → Markdown + LaTeX tables→ summary.md / summary.tex
```

---

## Step-by-step

### Step 01 — Build metrics

Builds each SFR CRUD repo with `docker compose build`, starts it, waits for
`/health`, then runs a full CRUD probe (POST/GET/GET-by-id/PUT/DELETE).

```bash
python3 experiment-scripts/01_collect_build_metrics.py
# optional overrides:
python3 experiment-scripts/01_collect_build_metrics.py \
    --matrix scripts/crud-matrix.yaml \
    --out    reproduced-experiments/results/crud-build-metrics.jsonl
```

**Output fields:** `name`, `language`, `framework`, `orm`, `port`, `passed`,
`error`, `build_time_s`, `crud_details`

---

### Step 02 — Repo stats

Counts source lines of code (LOC) using `repogen.core.collect_files` and reads
Docker image size + layer count from the local Docker daemon.

```bash
python3 experiment-scripts/02_collect_repo_stats.py
```

**Output fields:** `name`, `language`, `framework`, `orm`, `loc`, `files`,
`src_dir`, `docker_layers`, `image_size_mb`

Note: `image_size_mb` requires the image to have been built (run step 01 first,
or `docker compose build` in each repo directory).

---

### Step 03 — Generation method classification

Classifies each repo as `agent`-generated or `template`-generated.
All CRUD repos are agent-generated (no CRUD Jinja2 templates exist).

```bash
python3 experiment-scripts/03_classify_generation_method.py
```

**Output:** YAML with `sfr`, `monorepo`, and `summary` sections.

---

### Step 04 — Pilot identification

Sends the file tree, main source file, and docker-compose snippet for each repo
to Claude and asks it to identify the language, framework, ORM, database, and
port. Compares predictions against ground-truth from the matrix.

```bash
python3 experiment-scripts/04_run_pilot_identification.py

# use a different model:
python3 experiment-scripts/04_run_pilot_identification.py \
    --model claude-haiku-4-5-20251001
```

**Output fields:** `name`, `gt_language`, `pred_language`, `gt_framework`,
`pred_framework`, `gt_orm`, `pred_orm`, `gt_port`, `pred_port`, `pred_database`,
`lang_correct`, `fw_correct`, `orm_correct`, `port_correct`

---

### Step 05a — Sample real-world repos

Queries the GitHub Search API for repositories using framework + ORM keywords
per technology stack. Skips forks and archived repos.

```bash
# Run for each star threshold
python3 experiment-scripts/05a_sample_real_repos.py --min-stars 5
python3 experiment-scripts/05a_sample_real_repos.py --min-stars 4
python3 experiment-scripts/05a_sample_real_repos.py --min-stars 3

# custom output path:
python3 experiment-scripts/05a_sample_real_repos.py \
    --min-stars 5 \
    --out reproduced-experiments/results/real-repos-stars5.yaml
```

**Options:**
- `--min-stars N` — minimum GitHub star count (default: 5)
- `--years N` — only repos pushed within N years (default: 5)
- `--want N` — target repos per stack (default: 5; rarer stacks use smaller overrides)

**Output:** YAML keyed by `<language>-<framework>`, each with a `repos` list.

---

### Step 05b — Verify real-world repos

Shallow-clones each sampled repo, runs `docker compose build + up`, then probes
a set of common REST paths (`/items`, `/api/items`, `/health`, …).
"Passed" means the service started and responded to at least one probe path.

```bash
python3 experiment-scripts/05b_verify_real_repos.py \
    --sample   reproduced-experiments/results/real-repos-stars5.yaml \
    --out      reproduced-experiments/results/real-verify-stars5.jsonl \
    --clonedir /tmp/eval-crud-repos

# run all three thresholds:
for N in 3 4 5; do
  python3 experiment-scripts/05b_verify_real_repos.py \
      --sample   reproduced-experiments/results/real-repos-stars${N}.yaml \
      --out      reproduced-experiments/results/real-verify-stars${N}.jsonl \
      --clonedir /tmp/eval-crud-repos
done
```

Cloned repos are reused across runs (clonedir is not cleaned up automatically).

**Output fields:** `full_name`, `language`, `framework`, `orm`, `stars`,
`passed`, `build_time_s`, `has_dockerfile`, `has_compose`, `service_responded`,
`responded_path`, `http_code`, `error`

---

### Step 06 — Summary tables

Reads all result files and writes a Markdown summary and LaTeX table fragments.

```bash
python3 experiment-scripts/06_generate_summary_tables.py

# custom results dir or star thresholds:
python3 experiment-scripts/06_generate_summary_tables.py \
    --results reproduced-experiments/results \
    --stars 3 4 5
```

**Outputs:**
- `reproduced-experiments/results/summary.md` — human-readable summary with tables
- `reproduced-experiments/results/summary.tex` — LaTeX table fragments, paste into paper

Steps that haven't been run yet are shown as placeholder notes rather than failing.

---

## Running the full pipeline

```bash
# Prerequisites
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp env.example .env   # fill in ANTHROPIC_API_KEY and GITHUB_TOKEN

# Steps 01–04: synthetic repo experiments
python3 experiment-scripts/01_collect_build_metrics.py
python3 experiment-scripts/02_collect_repo_stats.py
python3 experiment-scripts/03_classify_generation_method.py
python3 experiment-scripts/04_run_pilot_identification.py

# Steps 05a+05b: real-world comparison (requires GITHUB_TOKEN + Docker)
for N in 3 4 5; do
  python3 experiment-scripts/05a_sample_real_repos.py --min-stars $N
  python3 experiment-scripts/05b_verify_real_repos.py \
      --sample   reproduced-experiments/results/real-repos-stars${N}.yaml \
      --out      reproduced-experiments/results/real-verify-stars${N}.jsonl \
      --clonedir /tmp/eval-crud-repos
done

# Step 06: generate summary
python3 experiment-scripts/06_generate_summary_tables.py
```

---

## Relationship to `evaluation/`

The `evaluation/` directory contains the original experiment scripts and results
from the paper. These `experiment-scripts/` are a cleaned-up, reproducible
rewrite that:

- Import from the `repogen` package rather than duplicating helpers
- Follow a consistent numbered naming scheme
- Default to `scripts/crud-matrix.yaml` and `reproduced-experiments/results/`
- Can be run independently (each script is self-contained)

The output formats are compatible with the originals so `summary.md` /
`summary.tex` can be compared directly against `evaluation/*/results/`.
