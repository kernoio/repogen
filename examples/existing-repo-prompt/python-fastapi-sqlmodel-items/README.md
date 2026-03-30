# Minimal FastAPI + PostgreSQL items API

Synthetic benchmark service: health probe, generic `items` CRUD, Alembic migrations, Docker Compose with PostgreSQL 16.

## Layout

- `src/app/http/` — FastAPI bootstrap, routers, middleware, global error handler
- `src/app/domain/` — item service layer
- `src/app/data/` — SQLModel table, engine, session dependency
- `src/app/migrations/` — Alembic environment and revisions
- `scripts/entrypoint.sh` — run migrations, then Gunicorn + Uvicorn workers

## Run locally (Docker)

The compose file maps host port **8000** to the app. Use the same port when smoke-testing (e.g. `scripts/verify.sh <this-dir> 8000` from the repogen repo root).

```bash
docker compose build && docker compose up -d
curl -sf http://localhost:8000/health
docker compose down
```

Default database URL (Compose): `postgresql://appuser:apppassword@db:5432/appdb`

## Development (optional)

Requires Python 3.11+, local PostgreSQL, and `DATABASE_URL` set. Install dependencies with `pip install -r requirements.txt`, run `alembic upgrade head`, then:

```bash
export PYTHONPATH=src
export DATABASE_URL=postgresql://appuser:apppassword@localhost:5432/appdb
uvicorn app.http.bootstrap:app --reload --host 0.0.0.0 --port 8000
```
