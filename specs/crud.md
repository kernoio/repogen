# Spec: CRUD Application

Generate a small, Dockerized CRUD service for each language/framework combination in the matrix.

## Required endpoints

| Method | Path         | Response | Description          |
|--------|--------------|----------|----------------------|
| GET    | /health      | 200 `{"status": "ok"}` | Health probe |
| POST   | /items       | 201 `{id, name, description, created_at}` | Create item |
| GET    | /items       | 200 `[{id, name, description}]` | List all items |
| GET    | /items/:id   | 200 `{id, name, description}` | Get single item |
| PUT    | /items/:id   | 200 `{id, name, description}` | Update item |
| DELETE | /items/:id   | 204 (no body) | Delete item |

## Item schema

```json
{
  "id": 1,
  "name": "string (required)",
  "description": "string (optional)",
  "created_at": "ISO 8601 datetime"
}
```

## Database

Use **PostgreSQL** (postgres:16-alpine) as the backing store. Add it as a named service in `docker-compose.yml` with a healthcheck and `depends_on: condition: service_healthy` on the application service.

Connection string: `postgresql://appuser:apppassword@db:5432/appdb`

## Repository structure

```
<repo-name>/
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── .gitignore
├── README.md
└── src/           # application source
```

## Naming convention

`crud-<language>-<framework>` — e.g., `crud-python-fastapi`, `crud-ts-express`

## Notes

- The `/health` endpoint should verify the database connection (ping or simple query)
- Return appropriate HTTP status codes: 404 if item not found, 400 for validation errors
- Keep the implementation minimal — no authentication, no pagination required
- Use the framework's idiomatic patterns (ORM, routing, etc.)
