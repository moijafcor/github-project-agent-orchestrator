FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
COPY scripts/ scripts/
COPY oauth/ oauth/
COPY templates/ templates/

RUN pip install --no-cache-dir -e ".[oauth]"

RUN mkdir -p /app/data

ENV OAUTH_DB_PATH=/app/data/.oauth.db

EXPOSE 8765 8766
