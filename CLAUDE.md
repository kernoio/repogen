# repogen — IDE Agent Context

This file gives Claude Code, Cursor, GitHub Copilot, and other IDE agents the context needed to work productively on this project. Read this before generating or modifying any repository.

---

## What this project does

repogen generates synthetic benchmark repositories: small, Dockerized services that expose a consistent HTTP API (health endpoint + optional CRUD endpoints) across a configurable matrix of languages, frameworks, and dependency stacks. The repos are used to test and benchmark agentic software systems.

---

## Valid repo structure (required files)

Every generated repo must contain:

```
<repo-name>/
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── .gitignore
├── README.md
└── src/        (or app/, or framework-conventional layout)
```

The `/health` endpoint (GET, returns `{"status": "ok"}` with HTTP 200) is **mandatory** in every repo.

---

## Generation modes

1. **Template path** (fast): A Jinja2 template exists in `templates/<language>-<framework>/`. Render it with `repogen generate --name <name>`. No API call needed.
2. **Agent path** (flexible): No template exists. `repogen generate` calls Claude via the Anthropic SDK with a structured prompt. The agent returns a JSON object of `{filename: content}` pairs. You can do the same interactively.

To generate a repo interactively, produce the files listed above for the target stack, following the conventions in this file.

---

## Docker conventions

| Language   | Builder image                        | Runtime image                       |
|------------|--------------------------------------|-------------------------------------|
| Python     | python:3.11-slim                     | (same)                              |
| TypeScript | node:20-alpine                       | (same)                              |
| JavaScript | node:20-alpine                       | (same)                              |
| Bun        | oven/bun:latest                      | (same)                              |
| Go         | golang:1.23-alpine                   | alpine:3.20                         |
| Rust       | rust:1.88-slim                       | debian:bookworm-slim                |
| Java       | gradle:8-jdk21                       | eclipse-temurin:21-jre              |
| Kotlin     | gradle:8-jdk17                       | eclipse-temurin:17-jre              |
| Ruby       | ruby:3.3-slim                        | (same)                              |
| C#         | mcr.microsoft.com/dotnet/sdk:8.0     | mcr.microsoft.com/dotnet/aspnet:8.0 |
| C++        | gcc:13                               | debian:bookworm-slim                |

- Alpine/slim images need `curl` installed for healthchecks: `apk add --no-cache curl` or `apt-get install -y --no-install-recommends curl`
- Use multi-stage builds for compiled languages (Go, Rust, C#, C++, Java, Kotlin)
- Use `npm install` not `npm ci` (templates do not include a lockfile)

## docker-compose.yml healthcheck (every service)

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:<port>/health"]
  interval: 10s
  timeout: 5s
  retries: 5
  start_period: 15s   # increase for JVM stacks (45s) and Rails (40s)
```

---

## Framework-specific patterns

- **FastAPI**: `src/main.py`; `uvicorn main:app --host 0.0.0.0 --port 8000 --app-dir src`
- **Flask**: `src/app.py`; `gunicorn app:app --bind 0.0.0.0:5000 --chdir src`
- **Django**: health view in `src/health/views.py` + `urls.py`
- **Express (TS)**: `src/index.ts`; `npm run build` → `node dist/index.js`
- **Express (JS)**: `src/index.js`; `node src/index.js`
- **NestJS**: `AppController` with `@Get("health")`
- **Bun + Express**: `src/index.ts`; `bun install` / `bun run src/index.ts`
- **Gin (Go)**: `main.go`; build binary → copy to alpine
- **Axum (Rust)**: `src/main.rs`; `cargo build --release` → copy to debian-slim
- **Ktor**: `Application.kt`; Gradle `shadowJar` fat JAR
- **Spring Boot**: `@GetMapping("/health")`; `./gradlew bootJar`
- **Rails**: `get "/health"` in `config/routes.rb`; `rails server -b 0.0.0.0`
- **ASP.NET Core**: `app.MapGet("/health", ...)` in `Program.cs`
- **Crow (C++)**: Download `crow_all.h` header directly; `libasio-dev`; link `libboost-system-dev` only (not libboost-all-dev, fails on ARM64)

---

## CRUD endpoint pattern (when spec requires CRUD)

All CRUD repos implement the same `/items` resource:

```
POST   /items              → 201 { id, name, description, created_at }
GET    /items              → 200 [ { id, name, description } ]
GET    /items/:id          → 200 { id, name, description }
PUT    /items/:id          → 200 { id, name, description }
DELETE /items/:id          → 204
```

Use Postgres as the database. Add the DB as a service in `docker-compose.yml` with `depends_on: condition: service_healthy`.

---

## Known fix patterns (for the fix-and-retry loop)

When Docker build or health probe fails, these are the most common causes:

| Error symptom | Fix |
|---|---|
| `prisma: error while loading shared libraries: libssl` | Add `openssl` to `apk add` in Dockerfile |
| Go build fails on `rogpeppe/go-internal` | Use `golang:1.23-alpine` or later |
| Rust link error with `libstdc++` | Use `rust:1.88-slim`; add `-static-libstdc++ -static-libgcc` to RUSTFLAGS |
| `AdonisJS: Cannot find module` | AdonisJS v6 requires CLI — replace with Express + Knex |
| `feathers is not a function` | FeathersJS v5 API changed — replace with plain Express + Sequelize |
| Flask `db.create_all()` race in multi-worker gunicorn | Use single worker: `--workers 1` |
| Rails `rails db:migrate` shows "Usage: rails new" | Use `bundle exec rake db:migrate` instead |
| C++ crow `.deb` install fails on ARM64 | Download `crow_all.h` header directly; use `libasio-dev` + `libboost-system-dev` |
| Ruby missing `libyaml-dev` | Add `libyaml-dev` to `apt-get install` |
| `yarn: not found` inside node:20-alpine Dockerfile | yarn is already in node:20-alpine — do NOT `npm install -g yarn` |
| `uv lock` fails: "missing entry in tool.uv.sources" | Add `[tool.uv.sources]` with `package = { workspace = true }` to dependent pyproject.toml |

---

## Progress tracking

```bash
python3 scripts/progress.py status          # view all statuses
python3 scripts/progress.py pending         # list pending repos
python3 scripts/progress.py set <name> done --verified
```

Always check progress.yaml before creating a repo. Skip repos with `status: done`.

---

## Verification

After creating a repo, verify it:

```bash
scripts/verify.sh generated/<repo-name> <port>
```

Or manually:
```bash
cd generated/<repo-name>
docker compose build && docker compose up -d && sleep 15
curl -f http://localhost:<port>/health
docker compose down
```

---

## Adding a new stack (interactive workflow)

1. Generate the repo files for the new stack in `generated/<repo-name>/`
2. Run `scripts/verify.sh` — iterate until it passes
3. Save the working files as a template in `templates/<language>-<framework>/`
4. Add the stack to `languages.yaml`
5. Future `repogen generate` calls will use the template automatically (no API call needed)

This workflow ensures that interactive prototyping compounds into the automated pipeline.

---

## languages.yaml structure (for reading supported stacks)

```yaml
languages:
  python:
    frameworks:
      fastapi:
        builder_image: python:3.11-slim
        internal_port: 8000
        template: python-fastapi   # maps to templates/python-fastapi/
```

If `template` is absent, the agent path is used. If you create a new template, add the `template` key.

---

## Output format (agent path)

When generating via the Anthropic SDK, the model is prompted to return a JSON object:

```json
{
  "Dockerfile": "FROM python:3.11-slim\n...",
  "docker-compose.yml": "services:\n  ...",
  "src/main.py": "from fastapi import FastAPI\n..."
}
```

repogen writes each key as a file path relative to the repo root.
