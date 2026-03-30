# Prompt: Architecture report (REST + minimal `items` flow)

Use this document as the **system or user instruction** when analyzing any codebase. The goal is a **design-level report** that another model or human can use to **recreate the REST architecture** with the minimal CRUD surface **defined in the benchmark section below**—without copying or exposing the original source.

---

## How to use

1. Paste the **“Instruction block”** below into your assistant (optionally as a system message).
2. Provide context: repository path, tarball, tree listing, or read-only access instructions.
3. The output is a **report**, not a dump of files. Optionally run a **second pass** with the same confidentiality rules to turn the report into a **greenfield example project** (see “Follow-up: example project”).

---

## Instruction block (copy from here)

You are producing an **API and platform architecture report** for a software codebase.

### Benchmark: CRUD `items` API (target to reproduce)

The report should align with this **minimal Dockerized CRUD service** contract. (Quoted for self-containment—the analyzed repository will not contain this file.)

**Required endpoints**

| Method | Path | Response | Description |
|--------|------|----------|-------------|
| GET | `/health` | 200 `{"status": "ok"}` | Health probe |
| POST | `/items` | 201 `{id, name, description, created_at}` | Create item |
| GET | `/items` | 200 `[{id, name, description}]` | List all items |
| GET | `/items/:id` | 200 `{id, name, description}` | Get single item |
| PUT | `/items/:id` | 200 `{id, name, description}` | Update item |
| DELETE | `/items/:id` | 204 (no body) | Delete item |

**Item schema**

```json
{
  "id": 1,
  "name": "string (required)",
  "description": "string (optional)",
  "created_at": "ISO 8601 datetime"
}
```

**Database**

- Use **PostgreSQL** (`postgres:16-alpine`) as the backing store.
- Add it as a named service in `docker-compose.yml` with a healthcheck and `depends_on: condition: service_healthy` on the application service.
- Connection string: `postgresql://appuser:apppassword@db:5432/appdb`

**Repository structure (example layout)**

```
<repo-name>/
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── .gitignore
├── README.md
└── src/           # application source
```

**Notes for a full reproduction**

- The `/health` endpoint should verify the database connection (ping or simple query).
- Return appropriate HTTP status codes: 404 if item not found, 400 for validation errors.
- Keep the implementation minimal — no authentication, no pagination required.
- Use the framework’s idiomatic patterns (ORM, routing, etc.).

**If the analyzed service has no database** (health-only baseline): a minimal alternative is GET `/health` → 200 `{"status": "ok"}`, no database, no `/items`—describe that separately only when it matches the codebase.

---

### Objective

Describe how the service exposes its **HTTP API** (REST-shaped where applicable) at the level of **structure, patterns, and technology choices**, so that someone could implement a **minimal equivalent** using the **benchmark contract above** (endpoints, item schema, Postgres, compose pattern).

- If the analyzed project uses another database, say so explicitly and map **concepts** (migrations, connection, pooling) to how you would implement the same on **PostgreSQL** for the example.
- If the product primarily uses **GraphQL, gRPC, RPC, or async messaging** instead of REST-style routes, describe those patterns and explain **conceptually** how the **benchmark REST table** would map (resource paths, request/response bodies)—without assuming the product already exposes REST.
- If the codebase has **no server-side HTTP surface** (e.g. library, CLI, mobile or static frontend only), state that clearly; mark affected sections **not applicable** or **low confidence**, and still describe the **benchmark** as the target for a standalone greenfield service so the report stays usable for follow-up generation.

### Strict confidentiality (no leakage)

- **Do not** copy **verbatim** source from the analyzed codebase (no paste-and-tweak of original files).
- **Do not** reproduce real file paths, class names, table names, env var names, secrets, internal URLs, or proprietary business terms from the repo unless they are **generic framework names** (e.g. “Express router”, “SQLAlchemy session”).
- **Do not** include stack traces, log lines, or configuration values that could identify the deployment.
- For non-code illustration, use **synthetic placeholders** where paths or URLs would otherwise echo the repo: e.g. `postgresql://user:pass@db:5432/dbname`, or describe “versioned path prefix” without the project’s real prefix.

### Code snippets (allowed): paraphrase + `items` topic

**Stack-agnostic phrasing:** Examples below may use **Node/Express-style** names (`res`, `locals`, `next`) as shorthand for “response object / request-scoped context / continuation.” When writing snippets, **use the idioms of the analyzed stack** (e.g. `HttpContext`, servlet filters, ASP.NET middleware, Phoenix plugs, `http.ResponseWriter`, Axum extractors)—still synthetic and renamed, still aligned with the benchmark paths and JSON shapes.

You **may** include **short code snippets** in the report when they help explain **how** the stack implements HTTP, persistence, or migrations—**only if all** of the following hold:

1. **Paraphrased, not transcribed** — Rewrite the idea in your own structure and wording; do not mirror the original line order or copy unique comments/strings from the repo.
2. **Renamed everywhere** — Types, functions, modules, variables, and table names must be **synthetic** and **different** from the analyzed project (e.g. `ItemRepository`, `items`, `create_item`; not the codebase’s real entity names).
3. **Pattern fidelity vs benchmark contract** — Snippets must do **both**:
   - **Handler structure and pipeline** (middleware order, where the handler stops, how JSON is emitted: e.g. `res.locals` + terminal serializer, interceptors, filters, `next()` to a responder) must mirror **what the codebase actually does**, using synthetic `/items` routes and `Item` fields—not a simplified “tutorial” style unless the product really responds that way (e.g. do **not** show bare `res.json` in the route as the primary success path if the product always funnels through a `respond` middleware or equivalent).
   - **URLs, HTTP methods, and success response bodies** for the minimal service must align with the **benchmark table** (`GET /health` → `200 {"status":"ok"}` with DB ping per notes; CRUD paths and JSON shapes as specified). When the product differs (e.g. `{ data, meta }` envelopes, non-standard health content-type or status rules), show the **product mechanism** in the snippet or adjacent bullets, and **explicitly note** what the minimal benchmark repo would return instead—do not silently blend behaviors.
4. **Short and partial** — Prefer a few lines to one short block per topic (e.g. route registration, one handler showing `locals` + `next`, one migration fragment for an `items` table). Avoid whole files. You may use **two** adjacent micro-snippets when needed: one for **middleware / response pipeline**, one for **service call**—still synthetic names only.
5. **Pattern label** — Immediately before or after each snippet, add **one line** stating what the snippet is demonstrating, e.g. *Pattern: `res.locals.payload` + `respond` middleware; success JSON shape follows benchmark below.* or *Pattern: product health status codes; benchmark success body is `{"status":"ok"}` only.*
6. **No contradiction with REST surface** — Snippets must **not** contradict **REST surface (conceptual)** (report section 2). If that section says responses go through a global serializer, the snippet must reflect that; do not substitute a contradictory minimal handler.
7. **Disclaimer** — Include: *Paraphrased illustration for the `items` example; not copied from the analyzed codebase.*

If a pattern cannot be shown without echoing the real domain, use **pseudocode or bullet steps** instead of a snippet.

**Health endpoint in snippets:** The benchmark requires a **simple JSON body** on success (`{"status":"ok"}`) and a DB check as in **Notes for a full reproduction**. If the product uses richer health (alternate media type, 503 rules, extra fields), describe that in prose or a **labeled** snippet as **product behavior**, and state clearly what the **greenfield benchmark** would implement.

### Code and examples rule (non-snippet)

Where snippets are not needed, prefer prose, diagrams, or bullet steps. Any illustrative names remain **synthetic** and **`items`-aligned** when demonstrating API behavior.

### Report structure (required sections)

Answer in this order. Use concise prose and bullet lists; avoid filler.

1. **Stack summary**  
   Language(s), runtime version if inferable, primary web framework (or **none** if not a web service), major libraries for HTTP, ORM/query layer (or raw SQL / embedded DB), validation, and any API documentation tooling (OpenAPI, etc.). Mark **not applicable** where the codebase is not a server.

2. **REST surface (conceptual)**  
   How routes or handlers are organized (flat vs nested, versioning, resource naming). How path parameters and request bodies are bound. How successful responses are produced at a **pattern** level (direct handler response vs request-scoped payload + terminal middleware vs filters/interceptors vs equivalent in the stack)—this must stay consistent with any code snippets. How errors map to HTTP status codes at a **pattern** level (e.g. “global exception handler returns JSON problem details”), not project-specific error payloads. If the product is not REST-oriented, describe the actual style and how it relates to the **benchmark** CRUD paths.

3. **`items`-shaped mapping**  
   Which existing resources or tables **most closely** correspond to a generic `Item { id, name, description, created_at }`. If none exist, say so and describe what would need to be **invented** for the minimal flow without naming real entities from the repo.

4. **Design patterns**  
   Layering (handlers/controllers → services → repositories), DI style, repository pattern, DTOs, middleware pipeline, transaction boundaries—only what is **evident** from structure; mark uncertainty as “inferred”.

5. **Imports and module layout**  
   How the project splits packages/modules (e.g. `api/`, `domain/`, `infra/`). How imports express layering (internal vs public packages). **No** long directory trees here—that belongs in **Folder architecture**.

6. **Folder architecture**  
   Physical **directory layout** at a design level: top-level areas (application source, tests, scripts, deploy assets, generated code, docs). Where HTTP handlers/routes live relative to domain logic, persistence, and DTOs. Where migrations, seeds, and static assets sit. Monorepo vs single service vs `src/` layout—**describe roles**, not the repo’s real folder names.  
   Include one **synthetic schematic tree** (3–8 lines, generic labels only), e.g. `app/http/`, `app/domain/`, `migrations/`—renamed to match **illustrative** structure, not copied paths. State the **entrypoint** file role (“main module boots HTTP server”) without quoting its real name.

7. **Database**  
   Engine, how connections are acquired, migration tool (Flyway, Alembic, Prisma migrate, etc.), and how schema changes are applied in deploy/Docker. Again: **patterns and tool names**, not real migration filenames or SQL from the project. If the project has **no database**, say so and map **PostgreSQL** concepts only for the **benchmark** greenfield case.

8. **Docker and orchestration**  
   Whether Dockerfiles exist, multi-stage or not, base images **at category level** (“Debian-slim Node runtime”), compose services (app, db, cache), healthchecks, ports, `depends_on` semantics—**without** copying compose content verbatim.

9. **Gaps for a minimal benchmark repo**  
   What you would **strip or replace** to get a small Postgres-backed `items` service (auth, extra domains, queues, etc.).

10. **Confidence**  
   For each major section, note **high / medium / low** confidence and what was **not** visible (e.g. only `Dockerfile` seen, no migrations in tree).

### Output constraints

- Maximum length: aim for **2–4 pages** of markdown unless the user asks for more detail.
- **Code snippets** are optional; when used, they must follow **Code snippets (allowed): paraphrase + `items` topic** above (pattern fidelity + benchmark-aligned paths/bodies, paraphrased, renamed, with pattern label and disclaimer).
- End with a **single paragraph** titled **“Example-project generation hint”**: one dense paragraph that a follow-up model can implement from **without** re-reading the codebase. It must name, in generic terms: **language/runtime**, **framework**, **layering** (e.g. routes → services → DB), **response pipeline** if non-trivial (e.g. locals + terminal JSON middleware vs direct handler response), **migration tool**, **Docker style** (multi-stage, process manager, base image category), and **folder roles** matching the synthetic schematic in **Folder architecture**. Still **no** real names from the analyzed product.

---

## Follow-up: example project (optional second prompt)

After you have the report, you can ask:

> Using only the architecture report above (not the original codebase), generate a **new minimal repository** that implements the **full benchmark contract** embedded in that report (endpoints, item schema, PostgreSQL, compose/health pattern, `src/` layout). Match the **reported** language, framework, layering, **response pipeline pattern** (e.g. middleware order, how success JSON is produced), **folder architecture**, migration tool, and Docker style. Strip features the report lists under **Gaps for a minimal benchmark repo**; do not reintroduce auth, GraphQL, or other removed complexity unless the benchmark requires it. All names, paths, and sample data must be **synthetic**. Include `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.gitignore`, `README.md`, and `src/` (or the framework’s conventional layout). Do not reference the analyzed product.
