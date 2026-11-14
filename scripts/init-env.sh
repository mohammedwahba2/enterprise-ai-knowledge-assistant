#!/usr/bin/env bash
# Generates a local .env with random secrets. Refuses to overwrite an existing file.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -e .env ]]; then echo ".env already exists; leaving it untouched." >&2; exit 0; fi
rand() { LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c "$1"; }
sed \
  -e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(rand 32)/" \
  -e "s/^APP_DB_PASSWORD=.*/APP_DB_PASSWORD=$(rand 32)/" \
  -e "s/^WORKER_DB_PASSWORD=.*/WORKER_DB_PASSWORD=$(rand 32)/" \
  -e "s/^REDIS_PASSWORD=.*/REDIS_PASSWORD=$(rand 32)/" \
  -e "s/^JWT_SECRET=.*/JWT_SECRET=$(rand 64)/" \
  -e "s/^S3_ACCESS_KEY=.*/S3_ACCESS_KEY=$(rand 20)/" \
  -e "s/^S3_SECRET_KEY=.*/S3_SECRET_KEY=$(rand 40)/" \
  .env.example > .env
chmod 600 .env
echo "Created .env with generated secrets (not committed; listed in .gitignore)."
