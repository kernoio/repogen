# repogen

Generate synthetic benchmark repositories from a spec and a list of languages and frameworks. Every generated repo is Dockerized, verified to build and run, and ready to push to a GitHub organisation.

repogen is built for teams that need curated, reproducible test datasets for agentic software systems — tools that are expected to work across many different languages, frameworks, and repo structures.

---

## Commands at a glance

| Command | What it does |
|---|---|
| `repogen init` | Read a spec + language list, plan all combinations, write `matrix.yaml` |
| `repogen generate` | Generate repos from `matrix.yaml` (templates where available, Claude API otherwise) |
| `repogen verify` | Build and probe a repo — by path, by name, or all unverified in matrix.yaml |
| `repogen fix_loop` | Verify a single repo; on failure send diagnostics to Claude to fix it and retry |
| `repogen from_spec` | Generate a repo from a `Repo-specs/` architecture document, then verify it |
| `repogen endpoints` | Count applications and HTTP endpoints in a repo; write results to `endpoints.yaml` |
| `repogen coverage` | Report language/framework/size coverage and write `gaps.md` |
| `repogen push` | Push verified repos to a GitHub org |
| `repogen status` | Show the generation and verification state of every repo |

---

## Ways to use repogen

### Mode 1 — CLI (automated, batch)

For generating large numbers of repos without manual intervention. Point it at a spec file and a language list; it plans the combinations, generates the repos (using Jinja2 templates where available, calling the Claude API for anything novel), verifies each one with Docker, and pushes verified repos to your GitHub org.

```bash
git clone https://github.com/kernoio/repogen && cd repogen
python3 -m venv .venv && source .venv/bin/activate && pip install -e .

# Generate all combinations from a spec
repogen init --spec specs/crud.md --langs languages.yaml
repogen generate
repogen verify
repogen push --org my-org
```

Best for: well-understood patterns at scale. All language/framework combinations in `languages.yaml` that have a template need no API key. Novel stacks require `ANTHROPIC_API_KEY`.

---

### Mode 2 — From a Repo-spec (single real-codebase target)

For generating a benchmark repo that faithfully mirrors the stack of a specific real codebase. Write (or generate) a `Repo-specs/` document describing the target's language, framework, ORM, patterns, and folder layout, then run:

```bash
repogen from_spec Repo-specs/example_spec.md
```

repogen sends the spec to Claude, which produces a minimal CRUD service using the exact stack and idioms described. `fix_loop` then verifies it and self-repairs any build or runtime failures automatically.

The spec doesn't need to be exhaustive before you generate. A working starting point will come back from even a partial spec, and you can open the result in your IDE and co-edit with the agent to refine patterns, fill gaps, or adjust structure. See [Writing a Repo-spec](#writing-a-repo-spec) for guidance on what to include.

To double-check the endpoints, use
```bash
repogen verify generated/example_spec <port>
```
Check the correct `<port>` from `docker-compose.yml` in the generated repo.
Note that `fix_loop` will also need this port.

---

### Mode 3 — IDE-native (interactive, agent-driven)

For complex repos, novel patterns, or edge cases that need human judgement. Open this project in VS Code, Cursor, or any IDE with Claude Code. The `CLAUDE.md` file gives the agent all the context it needs — conventions, Docker patterns, fix history, verification protocol — so you can start generating immediately.

```
git clone https://github.com/kernoio/repogen
code repogen

# Then talk to the agent:
# "Generate a Rust Axum repo with a Redis cache dependency"
# "Create an edge case: a Python repo with a broken Dockerfile"
# "Add Elixir/Phoenix to languages.yaml and generate the first repo"
```

This mode is also the natural next step after `repogen from_spec`: once the auto-generated repo builds and passes verification, open it in your IDE to co-write any structural refinements, swap out patterns, or add features that weren't in the spec. The agent reads both `CLAUDE.md` and the generated files, so it can continue from where `from_spec` left off without re-explaining the context.

Best for: repos that require structural decisions, edge cases where incorrectness is intentional, or prototyping new language/framework support before adding it to the template library.

---

### Mode 4 — Hybrid (recommended)

Both the CLI and IDE modes share the same `languages.yaml`, `progress.yaml`, and `templates/` directory. Work done interactively compounds into the automated pipeline:

1. Build a complex repo interactively in your IDE
2. Commit the working source as a template
3. Future `repogen generate` runs pick it up automatically — no API call needed

---

### Mode 5 — Claude Code CLI (headless agent)

For teams already using Claude Code as a development tool, repogen can be driven entirely from the Claude Code CLI (`claude`) without opening an IDE. Clone the repo and run Claude Code in print mode to generate individual repos non-interactively, or use it as a scriptable step in a CI pipeline.

```bash
git clone https://github.com/kernoio/repogen && cd repogen

# Generate a single repo non-interactively
claude --print "Read CLAUDE.md and languages.yaml. Generate a Kotlin/Ktor CRUD repo with Postgres in generated/crud-kotlin-ktor. Port 9050."

# Verify it
scripts/verify.sh generated/crud-kotlin-ktor 9050

# Generate an edge case
claude --print "Read CLAUDE.md and specs/edge-cases.md. Create an edge-missing-dockerfile-ruby-rails repo in generated/ with source code but no Dockerfile, and a README describing the intended failure."
```

Because `CLAUDE.md` is present, Claude Code reads all conventions, fix patterns, and expected output format automatically — no prompt engineering required. The same prompts work whether you type them interactively in the IDE or pipe them through the CLI.

**Using Claude Code CLI in a generation loop:**

```bash
for repo in $(python3 scripts/progress.py pending); do
  claude --print "Read CLAUDE.md. Generate $repo in generated/$repo following all conventions."
  scripts/verify.sh generated/$repo <port>
  python3 scripts/progress.py set $repo done --verified
done
```

**Requires:** Claude Code CLI installed (`npm install -g @anthropic-ai/claude-code`) and authenticated.

---

## Installation

```bash
git clone https://github.com/kernoio/repogen
cd repogen
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp env.example .env   # then fill in your API keys
```

A virtual environment is recommended — there is an unrelated package also named `repogen` on PyPI that will be picked up if you install into a shared environment.

`repogen.py` is a thin shim that can be run directly without installing the package (`python3 repogen.py <command>`) — useful if you prefer not to use a venv.

**Prerequisites:**
- Python 3.11+
- Docker and Docker Compose
- `gh` CLI (for pushing to GitHub: `brew install gh && gh auth login`)
- `ANTHROPIC_API_KEY` environment variable (for agent-based generation, `fix_loop`, and `from_spec`)

---

## Quick start

```bash
# 1. Install
git clone https://github.com/kernoio/repogen && cd repogen
python3 -m venv .venv && source .venv/bin/activate && pip install -e .

# 2. Initialise a project from the built-in CRUD spec
repogen init --spec specs/crud.md --langs languages.yaml

# 3. Generate repos
repogen generate

# 4. Verify all generated repos
repogen verify

# 5. See what's covered and what gaps remain
repogen coverage

# 6. Push verified repos to GitHub
repogen push --org my-github-org
```

---

## CLI reference

### `repogen init`

Reads a spec file and a language list, plans all combinations, and writes `matrix.yaml`.

```
repogen init --spec <spec> --langs <langs> [--output <dir>]

Options:
  --spec      Path to spec file (.md or .yaml)         [required]
  --langs     Path to languages.yaml                   [default: languages.yaml]
  --output    Output directory for generated repos     [default: generated]
```

### `repogen generate`

Generates repos from `matrix.yaml`. Uses Jinja2 templates where available; calls the Claude API for novel stacks.

```
repogen generate [--name <repo>] [--model <model>] [--force]

Options:
  --name      Generate only this repo (default: all pending)
  --model     Claude model for agent path               [default: claude-sonnet-4-6]
  --force     Re-generate even if already done
```

### `repogen verify`

Builds and probes a repo with Docker Compose. Captures build output, container logs, health probe, and full CRUD suite. Records result in `progress.yaml`.

Can be called in three ways:

```
repogen verify [<repo-path> [port]]

Arguments:
  repo-path   Path to a repo directory (for repos not in matrix.yaml)
  port        Host port (auto-read from matrix.yaml if omitted)

Options:
  --name        Verify a specific repo by name (port read from matrix.yaml)
  --wait        Seconds to wait for startup                [default: 30]
  --verbose, -v Show each HTTP probe request and response
```

```bash
# Direct path — works for any repo, including from_spec output
repogen verify generated/example_repo 8001

# Port auto-detected from matrix.yaml
repogen verify generated/example_repo

# By name
repogen verify --name crud-python-fastapi

# All unverified repos in matrix.yaml
repogen verify
```

### `repogen fix_loop`

Verifies a single repo with a full build → start → probe cycle. On failure, sends the complete diagnostics (build output, container logs, endpoint probe results) and all current repo files to Claude, applies the returned fix, and re-verifies. Repeats up to `--max-retries` times.

```
repogen fix_loop <repo-path> [port]

Arguments:
  repo-path   Path to the generated repo directory      [required]
  port        Host port (auto-read from matrix.yaml if omitted)

Options:
  --max-retries   Fix attempts before giving up          [default: 3]
  --model         Claude model                           [default: claude-sonnet-4-6]
  --wait          Seconds to wait for service startup    [default: 30]
  --verbose, -v   Show each HTTP probe request and response
```

```bash
repogen fix_loop generated/example_repo 8001
repogen fix_loop generated/crud-python-fastapi        # port auto-read from matrix.yaml
repogen fix_loop generated/sfr-go-gin 8003 --verbose --max-retries 5
```

### `repogen from_spec`

Generates a benchmark repo from a `Repo-specs/` architecture document. Calls Claude with the spec, the CRUD endpoint contract, and all Docker conventions from `CLAUDE.md`, then hands the result to `fix_loop` for verification and self-repair.

```
repogen from_spec <spec-path>

Arguments:
  spec-path   Path to a Repo-spec .md file              [required]

Options:
  --output        Parent directory for generated repos   [default: generated/]
  --name          Repo directory name                    [default: spec filename stem]
  --port          Host port                              [default: next free port from 8000]
  --model         Claude model                           [default: claude-sonnet-4-6]
  --no-fix        Write files and exit, skip verification
  --max-retries   fix_loop retry cycles                  [default: 3]
  --wait          Startup wait in seconds                [default: 30]
```

```bash
repogen from_spec Repo-specs/example_repo.md
repogen from_spec Repo-specs/example_repo.md --port 8005
repogen from_spec Repo-specs/example_repo.md --name example_repo-v2 --no-fix
repogen from_spec Repo-specs/example_repo.md --max-retries 5 --wait 45
```

### `repogen endpoints`

Counts the number of application services and HTTP endpoints in a generated repo. Applications are counted by parsing `docker-compose.yml` (infrastructure services like Postgres and Redis are excluded). Endpoints are counted by sending all source files to Claude and asking it to enumerate every route. Results are written to `endpoints.yaml` inside the repo directory.

```
repogen endpoints [<repo-path>]

Arguments:
  repo-path   Path to a repo directory

Options:
  --name TEXT    Analyse a repo by name (path read from matrix.yaml)
  --all          Analyse all verified repos in matrix.yaml
  --model TEXT   Claude model for endpoint analysis     [default: claude-sonnet-4-6]
  --output TEXT  Write combined results to this file    [default: <repo>/endpoints.yaml]
```

```bash
repogen endpoints generated/seapoint
repogen endpoints --name crud-python-fastapi
repogen endpoints --all
repogen endpoints --all --output results/endpoints.yaml
```

Example `endpoints.yaml` output:

```yaml
repo: seapoint
analysed_at: 2026-04-02T10:00:00+00:00
applications:
  count: 1
  services:
    - name: app
      image: (build)
      ports: ['8001']
endpoints:
  count: 6
  routes:
    - method: GET
      path: /health
      description: Returns {"status":"ok"} to confirm the service is running.
    - method: POST
      path: /items
      description: Creates a new item and returns it with HTTP 201.
    - method: GET
      path: /items
      description: Returns all items as a list.
    - method: GET
      path: /items/:id
      description: Returns a single item by ID, or 404 if not found.
    - method: PUT
      path: /items/:id
      description: Updates an existing item by ID.
    - method: DELETE
      path: /items/:id
      description: Deletes an item by ID and returns HTTP 204.
```

### `repogen coverage`

Reads `matrix.yaml` and reports language/framework/size coverage. Writes `gaps.md`.

```
repogen coverage [--report <file>]

Options:
  --report    Output file for gap report                [default: gaps.md]
```

### `repogen push`

Pushes verified repos to a GitHub org. Initialises git, creates the remote repo, and pushes.

```
repogen push --org <org> [--name <repo>] [--private]

Options:
  --org       GitHub org or username                    [required]
  --name      Push only this repo (default: all verified)
  --private   Create private repos
```

### `repogen status`

Shows the current generation/verification state of all repos.

```
repogen status
```

---

## Writing a Repo-spec

A Repo-spec is a markdown document in `Repo-specs/` that describes a real codebase in enough detail for Claude to produce a faithful minimal replica. It is the input to `repogen from_spec`.

The goal is not a complete audit of the codebase. It is a targeted description of the parts that matter for generating a working CRUD benchmark: the stack, the idioms, and exactly what a minimal service built in that style looks like.

**You don't need to complete the spec before generating.** `repogen from_spec` will produce a working starting point from even a partial document. Once the repo builds and passes verification, open it in your IDE and use the agent to co-write the refinements — adjusting patterns, filling structural gaps, or making the generated code closer to the real codebase's style. A spec is a brief, not a contract.

---

### Sections that matter most

**Stack summary**

A short table of the key technology choices. Language, runtime, and version; web framework (and any decorator/routing libraries on top); ORM name, version, and style (active-record vs data-mapper); database engine and migration tooling.

Auth, background jobs, and observability are worth a single line each so Claude knows what to strip.

**REST surface**

How the framework routes requests and shapes responses:

- How controllers are declared — class-based with decorators, plain functions, etc.
- How path params, query params, and request bodies are extracted
- What a success response looks like end-to-end: does the handler return directly, or is there a terminal responder/interceptor?
- What an error response looks like — global error handler, middleware, HTTP status mapping

This tells Claude how to write the controller and wire up the error handler. Without it, you'll often get a structurally correct but idiomatically wrong result.

**Items-shaped mapping**

Describe explicitly how a generic `Item { id, name, description, created_at }` entity maps onto this codebase's patterns:

- What base class or mixins the entity would extend
- What the primary key looks like — auto-increment int, UUID, prefixed TypeID, etc.
- Whether timestamps come from the ORM or application code
- Which fields carry which decorators or validators

This is the section most likely to determine whether the generated entity code is actually idiomatic.

**Folder architecture**

The directory tree, with a one-line label per folder. Include only the server-side layout. The entry-point file path is the most important single line.

**Docker and orchestration**

How the Dockerfile is structured (single-stage vs multi-stage, base image), what compose services exist, the healthcheck approach, and any startup sequencing — e.g. run migrations before the server starts. This section maps directly onto `Dockerfile` and `docker-compose.yml`.

**Gaps analysis**

What you would strip from the full codebase to reach a minimal benchmark: auth middleware, background job systems, observability stacks, adapter layers, client SPAs. Being explicit here prevents Claude from including things it doesn't need and keeps the generated repo minimal.

---

### The generation hint (highest-value section)

End the spec with a section called `Example-project generation hint` or similar. Write it as a direct prose brief — as if you're describing the service to a developer who will build it from scratch. Mention:

- Language, runtime, and framework versions
- Routing and controller approach
- ORM and migration strategy
- Database compose pattern
- Dockerfile structure (multi-stage, base image, exposed port)
- Startup sequencing (migrate on start, etc.)
- Folder layout for the generated repo

This section is used verbatim as part of the generation prompt. The more concrete and specific it is, the more closely the output will match the target codebase's style, and the fewer `fix_loop` cycles will be needed. Code snippets alongside this section — paraphrased examples of the controller pattern, entity definition, and health endpoint — are not required but typically eliminate one or two repair cycles.

---

### Example spec structure

```
Repo-specs/MyApp.md
├── 1. Stack summary              ← table: language, framework, ORM, DB, auth, jobs
├── 2. REST surface               ← routing, parameter binding, response/error shape
├── 3. Items-shaped mapping       ← how Item entity looks in this codebase's style
├── 4. Design patterns            ← layering, DI, DTOs, transactions, middleware order
├── 5. Folder architecture        ← directory tree with labels; highlight entry point
├── 6. Database                   ← engine, driver, ORM, migrations, ID strategy
├── 7. Docker and orchestration   ← Dockerfile structure, compose services, healthcheck
├── 8. Gaps analysis              ← what to strip for the benchmark
├── 9. Code snippets              ← (optional) paraphrased controller, entity, health
└── 10. Example-project generation hint  ← direct build brief (most important)
```

---

## Spec files

A spec (`specs/`) describes what endpoints and behaviour every generated repo must implement, independent of language or framework.

```markdown
# CRUD API spec

Each repository implements a minimal CRUD REST API for an Item entity
(id, name, description, created_at) backed by Postgres.

Required endpoints:
- GET  /health       → {"status": "ok"}
- POST /items        → 201
- GET  /items        → 200 list
- GET  /items/:id    → 200 or 404
- PUT  /items/:id    → 200 or 404
- DELETE /items/:id  → 204 or 404
```

See `specs/` for examples: `healthcheck.md`, `crud.md`, `edge-cases.md`.

---

## languages.yaml

Defines every supported language, its frameworks, Docker base images, internal port, and start period.

```yaml
languages:
  - name: python
    frameworks:
      - name: fastapi
        template: python-fastapi
      - name: django
      - name: flask
        template: python-flask
    builder_image: python:3.11-slim
    runtime_image: python:3.11-slim
    default_internal_port: 8000
    healthcheck_start_period: 30
```

If a `template` key is present, `repogen generate` renders the Jinja2 template and makes no API call. If absent, the Claude agent path is used.

---

## Examples

The `examples/` directory contains pre-built, verified repos that serve as concrete reference for the agent in IDE-native and Claude Code CLI modes:

| Repo | Stack | Pattern |
|------|-------|---------|
| `examples/crud-python-fastapi` | Python + FastAPI + Postgres | Interpreted language, pip deps, uvicorn |
| `examples/crud-go-gin` | Go + Gin + Postgres | Compiled multi-stage build, static binary |

These are real repos from the generated dataset — built, verified, and committed as reference. When Claude Code generates a new repo it hasn't seen before, it reads these examples alongside `CLAUDE.md` to understand the expected structure, rather than relying on instructions alone.

To add more examples (recommended for new language families):

```bash
cp -r generated/crud-ruby-rails examples/crud-ruby-rails
git add examples/crud-ruby-rails
git commit -m "examples: add Ruby/Rails reference"
```

---

## Templates

Templates live in `templates/<name>/` and contain the complete file tree for a single-service repo. Files ending in `.j2` are rendered with Jinja2; all other files are copied as-is.

**Template variables:**

| Variable | Example |
|---|---|
| `{{ repo_name }}` | `crud-python-fastapi` |
| `{{ language }}` | `python` |
| `{{ framework }}` | `fastapi` |
| `{{ port }}` | `9000` |
| `{{ internal_port }}` | `8000` |
| `{{ orm }}` | `sqlalchemy` |

To add a new template, create `templates/<name>/` and add the `template` key to `languages.yaml`.

---

## CLAUDE.md — IDE-native mode

The `CLAUDE.md` at the project root gives an IDE agent (Claude Code, Cursor, Copilot) all the context it needs to generate and verify repos interactively, without re-explaining conventions in each session. It covers:

- What a valid generated repo looks like
- Docker conventions per language (base images, ports, healthcheck patterns)
- The verification protocol
- Known fix patterns for common build failures
- How to update `languages.yaml` and `progress.yaml`

For interactive use, open this project in your IDE and the agent will read `CLAUDE.md` automatically.

---

## How generation works

```
repogen generate
│
├── For each combination in matrix.yaml:
│   ├── Template exists? ──── YES ──→ Render Jinja2 template → write to generated/<name>/
│   └── No template ─────── NO ───→ Call Claude API → agent writes all files
│
repogen verify  /  repogen fix_loop
│
├── docker compose build          (capture output on failure)
├── docker compose up -d
├── wait for startup
├── docker compose logs           (always captured)
├── probe GET /health
├── probe CRUD endpoints          (if /items route exists)
└── on failure → send diagnostics + all repo files to Claude
                → apply returned fix → retry (up to --max-retries)

repogen from_spec
│
├── Send Repo-spec + CRUD contract + CLAUDE.md conventions to Claude
├── Write returned {filename: content} to generated/<name>/
└── Hand off to fix_loop for verification and self-repair
    └── On pass: open in IDE for any structural refinements (optional)
```

---

## Known fix patterns

When `fix_loop` encounters a build failure, it passes the full diagnostics to Claude for diagnosis. The following patterns are in the knowledge base from prior generation runs:

| Stack | Symptom | Fix |
|---|---|---|
| Any / Alpine | Prisma: `libssl` not found | Add `openssl` to `apk add` |
| Go | `rogpeppe/go-internal` build error | Use `golang:1.23-alpine` or later |
| Rust | `GLIBCXX_3.4.32` not in `debian:bookworm-slim` | Add `-static-libstdc++ -static-libgcc` to RUSTFLAGS |
| Ruby Rails | `rails db:migrate` shows help instead of running | Use `bundle exec rake db:migrate` |
| Ruby | `psych` gem fails to install | Add `libyaml-dev` to apt-get |
| C++ Crow | `.deb` package is x86-only | Download `crow_all.h` header directly |
| C++ Crow | `libboost-all-dev` fails on ARM64 | Use `libboost-system-dev` only |
| Flask (CRUD) | Race condition with `db.create_all()` in multi-worker gunicorn | Use `--workers 1` |
| AdonisJS | `Cannot find module` at runtime | Replace with Express + Knex |
| node:20-alpine | `yarn: not found` | yarn is pre-installed — remove the `npm install -g yarn` line |

---

## Reproducing the paper experiments

The `experiment-scripts/` directory contains a numbered pipeline that reproduces the results from the accompanying paper. Each script is self-contained and writes results to `reproduced-experiments/results/`.

```bash
python3 experiment-scripts/01_collect_build_metrics.py   # build + CRUD-test all repos
python3 experiment-scripts/02_collect_repo_stats.py      # LOC + Docker image stats
python3 experiment-scripts/03_classify_generation_method.py
python3 experiment-scripts/04_run_pilot_identification.py  # Claude identifies stack from repo
python3 experiment-scripts/05a_sample_real_repos.py --min-stars 5
python3 experiment-scripts/05b_verify_real_repos.py \
    --sample reproduced-experiments/results/real-repos-stars5.yaml \
    --out    reproduced-experiments/results/real-verify-stars5.jsonl \
    --clonedir /tmp/eval-crud-repos
python3 experiment-scripts/06_generate_summary_tables.py  # → summary.md + summary.tex
```

See [experiment-scripts/README.md](experiment-scripts/README.md) for full documentation.

---

## Contributing

To add support for a new language or framework:

1. Create a template in `templates/<name>/`
2. Add the language/framework to `languages.yaml`
3. Run `repogen generate --name <new-repo>` to test it
4. Run `repogen fix_loop generated/<new-repo>` to verify and self-repair
5. Submit a PR

For edge cases and experimental patterns, use IDE-native mode to prototype first, then commit the working files as a template.

---

## Background

repogen was built to support automated benchmarking of agentic software systems across diverse technology stacks. Modern software products are expected to work across many different languages and frameworks; agents make building cross-stack systems easier, but they must be tested on datasets that genuinely span that space.

The dataset generated by repogen covers:
- 11 languages, 16+ language/framework combinations (single-service repos)
- Monorepos with 2–11 services in uniform and polyglot configurations
- All 55 possible language pairs represented
- Workspace detection examples (pnpm, yarn, Python uv)

See [combination-coverage.md](https://github.com/kernoio/repogen/blob/main/combination-coverage.md) for the full coverage map.

---

## License

MIT
