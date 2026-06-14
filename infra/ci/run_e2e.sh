#!/usr/bin/env bash
# E2e Playwright contra el artefacto real: la imagen edge (SPA horneado + gateway que
# proxea /api), same-origin, levantada con compose. Sirve para `make e2e` y el job de CI.
# El navegador de Playwright necesita libs de sistema (sudo) → corre en CI con
# `npx playwright install --with-deps`; en el WSL2 sin sudo, no.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
KEYS="$ROOT/infra/keys"

# auth corre como ${UID}:${GID} para leer la clave 0600 montada (problemas-resueltos #18).
# `env UID=…` esquiva el UID de solo-lectura de bash y funciona con cualquier uid de runner.
COMPOSE=(env "UID=$(id -u)" "GID=$(id -g)" docker compose
  -f infra/docker-compose.yml -f infra/docker-compose.edge.yml)

# 1. Claves RS256 (auth firma, transactions verifica)
if [[ ! -f "$KEYS/jwt-private.pem" ]]; then
  mkdir -p "$KEYS"
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$KEYS/jwt-private.pem"
  openssl pkey -in "$KEYS/jwt-private.pem" -pubout -out "$KEYS/jwt-public.pem"
fi

# 2. Stack con la imagen edge (SPA + /api en :8080). El compose ordena: mongo →
#    mongo-init (RS PRIMARY) → auth/transactions (bootstrap de usuarios demo) → edge.
"${COMPOSE[@]}" up -d --build

# 3. Esperar a que el API responda por el edge (todo listo)
for _ in $(seq 1 60); do
  curl -sf http://localhost:8080/api/health >/dev/null 2>&1 && break
  sleep 2
done
curl -sf http://localhost:8080/api/health >/dev/null || {
  echo "El stack no respondió en :8080/api/health"; "${COMPOSE[@]}" logs --tail=40; exit 1
}

# 4. Seed pequeño (5% EN_REVISION → siempre hay una para aprobar)
( cd infra/seed && uv run seed.py --count 2000 --drop )

# 5. E2e
( cd frontend && npx playwright test )

echo "E2e OK."
