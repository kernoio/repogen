# crud-go-gin

Go + Gin + GORM + PostgreSQL CRUD example.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| GET | /items | List all items |
| POST | /items | Create item |
| GET | /items/{id} | Get one item |
| PUT | /items/{id} | Update item |
| DELETE | /items/{id} | Delete item |

## Run

```bash
docker compose up --build
curl http://localhost:9030/health
curl -X POST http://localhost:9030/items \
  -H 'Content-Type: application/json' \
  -d '{"name":"hello","description":"world"}'
```
