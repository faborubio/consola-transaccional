#!/usr/bin/env bash
# Re-siembra los datos demo para que las mutaciones de los visitantes no ensucien la demo
# pública (datos ficticios). Corre el seed en un contenedor uv sobre la red de compose —
# no necesita Python/uv en el host de la VM. Sirve para el seed inicial y para el cron.
set -euo pipefail

NET="${COMPOSE_NET:-consola-transaccional_backend}"
REPO="${REPO_DIR:-/opt/consola}"
COUNT="${SEED_COUNT:-500000}"

docker run --rm --network "$NET" -v "$REPO/infra/seed:/seed:ro" \
  ghcr.io/astral-sh/uv:python3.12-bookworm-slim \
  uv run /seed/seed.py \
    --uri "mongodb://mongo:27017/?replicaSet=rs0&directConnection=true" \
    --count "$COUNT" --drop

echo "Reseed completo: $COUNT transacciones demo."
