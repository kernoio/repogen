FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

COPY src/ ./src/

ENV PYTHONPATH=/app/src
ENV WEB_CONCURRENCY=2

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
