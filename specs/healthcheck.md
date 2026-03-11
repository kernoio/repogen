# Spec: Health Endpoint Only

Generate a minimal, Dockerized HTTP service with a single `/health` endpoint for each language/framework combination in the matrix.

## Required endpoints

| Method | Path    | Response | Description |
|--------|---------|----------|-------------|
| GET    | /health | 200 `{"status": "ok"}` | Health probe |

## No database required

These repos have no database dependency. The service should start and respond to `/health` with no external services.

## Repository structure

```
<repo-name>/
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── .gitignore
├── README.md
└── src/
```

## Naming convention

`sfr-<language>-<framework>` — e.g., `sfr-python-fastapi`, `sfr-ts-express`

## Notes

- Keep the implementation as minimal as possible — just enough to serve `/health`
- The Dockerfile should be production-ready (non-root user, minimal layers)
- Include a `docker-compose.yml` healthcheck on `/health`
