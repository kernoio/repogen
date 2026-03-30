#!/bin/sh
set -e
export PYTHONPATH="/app/src"
cd /app
alembic upgrade head
exec gunicorn \
  -k uvicorn.workers.UvicornWorker \
  -w "${WEB_CONCURRENCY:-2}" \
  -b 0.0.0.0:8000 \
  --chdir /app/src \
  app.http.bootstrap:app
