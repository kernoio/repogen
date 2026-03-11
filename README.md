# repogen

Generate synthetic benchmark repositories from a spec and a list of languages and frameworks. Every generated repo is Dockerized, verified to build and run, and pushed to a GitHub organisation.

Built for teams that need curated, reproducible test datasets for agentic software systems — tools that are expected to work across many different languages, frameworks, and repo structures.

---

## Two ways to use repogen

### Mode 1 — CLI (automated, batch)

For generating large numbers of repos without manual intervention. Point it at a spec file and a language list; it plans the combinations, generates the repos (using Jinja2 templates where available, calling the Claude API for anything novel), verifies each one with Docker, and pushes verified repos to your GitHub org.

```bash
pip install repogen

# Generate all combinations from a spec
repogen generate --spec specs/crud.md --langs languages.yaml --org my-org

# Check what was built and what's missing
repogen coverage

# Push verified repos
repogen push --org my-org
```

Best for: well-understood patterns at scale. All 16 language/framework combinations in this repo's default `languages.yaml` have templates — no API key needed for those. Novel stacks and edge cases require `ANTHROPIC_API_KEY`.

---

### Mode 2 — IDE-native (interactive, agent-driven)

For complex repos, novel patterns, or edge cases that need human judgement. Open this project in VS Code, Cursor, or any IDE with Claude Code or a similar agent. The `CLAUDE.md` file gives the agent all the context it needs — conventions, Docker patterns, fix history, verification protocol — so you can start generating immediately.

```
# In your IDE terminal:
git clone https://github.com/kernoio/repogen
code repogen          # opens in VS Code with Claude Code

# Then just talk to the agent:
# "Generate a Rust Axum repo with a Redis cache dependency"
# "Create an edge case: a Python repo with a broken Dockerfile"
# "Add Elixir/Phoenix to languages.yaml and generate the first repo"
```

Best for: repos that require structural decisions, edge cases where incorrectness is intentional, or prototyping new language/framework support before adding it to the template library.

---

### Mode 3 — Hybrid (recommended)

Both modes share the same `languages.yaml`, `progress.yaml`, and `templates/` directory. Work done interactively compounds into the automated pipeline:

1. Build a complex repo interactively in your IDE
2. Commit the working source as a template
3. Future `repogen generate` runs pick it up automatically

---

## Installation

```bash
pip install repogen

# Or from source:
git clone https://github.com/kernoio/repogen
cd repogen
pip install -e .
```

**Prerequisites:**
- Python 3.11+
- Docker and Docker Compose
- `gh` CLI (for pushing to GitHub: `brew install gh && gh auth login`)
- `ANTHROPIC_API_KEY` environment variable (for agent-based generation only)

---

## Quick start

```bash
# 1. Install
pip install repogen

# 2. Initialise a project from the built-in CRUD spec
repogen init --spec specs/crud.md --langs languages.yaml --output my-dataset

# 3. Generate repos (uses templates for known stacks, Claude API for unknown)
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

Reads a spec file and a language list, plans all combinations, and writes a `matrix.yaml`.

```
repogen init --spec <spec> --langs <langs> [--output <dir>]

Options:
  --spec      Path to spec file (.md or .yaml)         [required]
  --langs     Path to languages.yaml                   [default: languages.yaml]
  --output    Output directory for generated repos     [default: generated]
```

### `repogen generate`

Generates repos from `matrix.yaml`. Uses Jinja2 templates where available; calls Claude API for novel stacks.

```
repogen generate [--name <repo>] [--model <model>] [--force]

Options:
  --name      Generate only this repo (default: all pending)
  --model     Claude model for agent path               [default: claude-sonnet-4-6]
  --force     Re-generate even if already done
```

### `repogen verify`

Runs `docker compose build`, starts services, and probes endpoints. Records result in `progress.yaml`.

```
repogen verify [--name <repo>] [--wait <seconds>]

Options:
  --name      Verify only this repo (default: all unverified)
  --wait      Seconds to wait for startup                [default: 30]
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
repogen push [--org <org>] [--name <repo>] [--private]

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

## Spec files

A spec is a plain markdown or YAML file describing the type of repos to generate.

**Markdown spec (natural language):**

```markdown
# CRUD API spec

Each repository should implement a minimal CRUD REST API for an `Item` entity
(id, name, description, created_at) backed by Postgres.

Required endpoints:
- GET  /health       → {"status": "ok"}
- POST /items        → 201
- GET  /items        → 200 list
- GET  /items/:id    → 200 or 404
- PUT  /items/:id    → 200 or 404
- DELETE /items/:id  → 204 or 404

Every service must be Dockerized with a docker-compose.yml that includes
a Postgres dependency with a healthcheck.
```

See `specs/` for examples: `healthcheck.md`, `crud.md`, `edge-cases.md`.

---

## languages.yaml

Defines every supported language, its frameworks, Docker base images, internal port, and start period. Drives both the template path and the agent prompt.

```yaml
languages:
  - name: python
    frameworks:
      - name: fastapi
        template: python-fastapi
      - name: django
        template: python-django
      - name: flask
        template: python-flask
    builder_image: python:3.11-slim
    runtime_image: python:3.11-slim
    default_internal_port: 8000
    healthcheck_start_period: 30

  - name: typescript
    frameworks:
      - name: express
        template: ts-express
      - name: nestjs
        template: ts-nestjs
      - name: feather
        template: ts-feather
      - name: adonis
        template: ts-adonis
    builder_image: node:20-alpine
    runtime_image: node:20-alpine
    default_internal_port: 3000
    healthcheck_start_period: 30
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

To add a new template, create `templates/<name>/` and add it to `languages.yaml`.

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
│
│   ├── Template exists? ──── YES ──→ Render Jinja2 template
│   │                                     └── Write files to generated/<name>/
│   │
│   └── No template ─────── NO ───→ Call Claude API
│                                       └── Agent writes all files
│
├── repogen verify
│   ├── docker compose build
│   ├── docker compose up -d
│   ├── wait for startup
│   ├── probe endpoints (GET /health, CRUD endpoints per spec)
│   └── if fail → call Claude API with error → apply patch → retry (up to 3x)
│
└── repogen push
    ├── git init + commit
    ├── gh repo create <org>/<name>
    └── git push
```

---

## Known fix patterns

When the agent-based path encounters a build failure, repogen passes the error to Claude for diagnosis. The following patterns are in the knowledge base from prior generation runs:

| Stack | Known issue | Fix |
|---|---|---|
| Any / Alpine | Prisma requires `openssl` | Add `openssl` to `apk add` |
| Go | `rogpeppe/go-internal` requires Go 1.23+ | Use `golang:1.23-alpine` |
| Rust | `GLIBCXX_3.4.32` not in `debian:bookworm-slim` | Static link: `-static-libstdc++ -static-libgcc` |
| Ruby Rails | `rails db:migrate` shows help instead of running | Use `bundle exec rake db:migrate` |
| Ruby Rails | `psych` gem fails to install | Add `libyaml-dev` to apt-get |
| C++ Crow | `.deb` package is x86-only | Download `crow_all.h` header directly |
| C++ Crow | `libboost-all-dev` fails on ARM64 | Use `libboost-system-dev` only |

---

## Contributing

To add support for a new language or framework:

1. Create a template in `templates/<name>/`
2. Add the language/framework to `languages.yaml`
3. Run `repogen generate --name <new-repo>` to test it
4. Run `repogen verify --name <new-repo>` to confirm
5. Submit a PR

For edge cases and experimental patterns, use IDE-native mode to prototype first, then commit the working files as a template.

---

## Background

repogen was built to support automated benchmarking of agentic software systems across diverse technology stacks. Modern software products are expected to work across many different languages and frameworks; agents make building cross-stack systems easier, but they must be tested on datasets that genuinely span that space.

The dataset generated by repogen covers:
- 11 languages, 16 language/framework combinations (single-service repos)
- Monorepos with 2–11 services in uniform and polyglot configurations
- All 55 possible language pairs represented
- Workspace detection examples (pnpm, yarn, Python uv)

See [combination-coverage.md](https://github.com/kernoio/repogen/blob/main/combination-coverage.md) for the full coverage map.

---

## License

MIT
