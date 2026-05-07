#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
docker compose -f "$COMPOSE_FILE" up -d postgres

echo "Waiting for PostgreSQL..."
until docker compose -f "$COMPOSE_FILE" exec -T postgres \
    pg_isready -U sdd -d sdd -q; do
    sleep 1
done

export SDD_DATABASE_URL="postgresql://sdd:sdd@localhost:5432/sdd"
echo "PG ready. SDD_DATABASE_URL=$SDD_DATABASE_URL"
echo "Run: SDD_DATABASE_URL=$SDD_DATABASE_URL pytest tests/integration/ -m pg -v"
