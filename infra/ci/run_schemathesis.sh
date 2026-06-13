#!/usr/bin/env bash
# Schemathesis con autenticación real contra ambos servicios (Fase 6).
#
# Estrategia: Mongo (replica set) y Redis vienen de compose (ya publican 27017/6379);
# los dos apps FastAPI corren en el HOST con uv contra esos datastores, y Schemathesis
# les pega DIRECTO (no por el gateway: su rate-limit 20r/s ahogaría al fuzzer con 429).
# El hook (infra/ci/schemathesis_hooks.py) hace login en auth e inyecta el bearer en
# cada request. Sirve igual en local (`make schemathesis`) y en CI.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

COMPOSE="docker compose -f infra/docker-compose.yml"
AUTH_PORT=8001
TXN_PORT=8002
KEYS="$ROOT/infra/keys"
PIDS=()

cleanup() {
  for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT

# 1. Claves RS256 (auth las necesita para firmar; transactions la pública para verificar)
if [[ ! -f "$KEYS/jwt-private.pem" ]]; then
  mkdir -p "$KEYS"
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$KEYS/jwt-private.pem"
  openssl pkey -in "$KEYS/jwt-private.pem" -pubout -out "$KEYS/jwt-public.pem"
fi

# 2. Mongo replica set + Redis desde compose
$COMPOSE up -d redis
$COMPOSE run --rm mongo-init   # arranca mongo (espera healthcheck), inicia rs0, sale

# 3. Apps en el host (mismas claves → el token de auth lo valida transactions)
( cd services/auth && uv sync --frozen >/dev/null && \
  AUTH_MONGO_URI="mongodb://localhost:27017/?replicaSet=rs0&directConnection=true" \
  AUTH_MONGO_DB="auth_db_st" \
  AUTH_JWT_PRIVATE_KEY_FILE="$KEYS/jwt-private.pem" \
  AUTH_JWT_PUBLIC_KEY_FILE="$KEYS/jwt-public.pem" \
  uv run uvicorn app.main:app --host 127.0.0.1 --port $AUTH_PORT ) &
PIDS+=($!)

( cd services/transactions && uv sync --frozen >/dev/null && \
  TXN_MONGO_URI="mongodb://localhost:27017/?replicaSet=rs0&directConnection=true" \
  TXN_MONGO_DB="transactions_db_st" \
  TXN_JWT_PUBLIC_KEY_FILE="$KEYS/jwt-public.pem" \
  TXN_REDIS_URI="redis://localhost:6379/0" \
  uv run uvicorn app.main:app --host 127.0.0.1 --port $TXN_PORT ) &
PIDS+=($!)

# 4. Esperar readiness de ambos /health
for url in "http://localhost:$AUTH_PORT/health" "http://localhost:$TXN_PORT/health"; do
  for _ in $(seq 1 30); do
    curl -sf "$url" >/dev/null 2>&1 && break
    sleep 1
  done
  curl -sf "$url" >/dev/null || { echo "Timeout esperando $url"; exit 1; }
done

# 5. Schemathesis sobre cada esquema, autenticado por el hook.
# venv dedicado + binario DIRECTO con PYTHONPATH. NO `uv run --with`: el uv nuevo (que
# instala setup-uv v8) NO propaga PYTHONPATH al subproceso → el hook no se cargaba en CI
# y el fuzzing corría SIN auth (todo 401: teatro verde, justo lo que el hook evita).
# Pinado a 4.21.5 por reproducibilidad (como el openapi-generator).
ST_VENV="$(mktemp -d)/st-venv"
uv venv "$ST_VENV" >/dev/null
uv pip install --python "$ST_VENV" 'schemathesis==4.21.5' requests >/dev/null

run_st() {
  local name="$1" port="$2"
  echo "=== Schemathesis: $name (puerto $port) ==="
  # --suppress-health-check en la CLI: el mismo ajuste en schemathesis.toml se carga
  # pero NO se propaga a la fase Fuzzing. `filter_too_much` es ruido del generador en
  # operaciones sin parámetros o con {id} de patrón restrictivo sin datos sembrados.
  SCHEMATHESIS_HOOKS=schemathesis_hooks \
  PYTHONPATH="$ROOT/infra/ci" \
  AUTH_BASE_URL="http://localhost:$AUTH_PORT" \
  "$ST_VENV/bin/schemathesis" run "http://localhost:$port/openapi.json" \
    --url "http://localhost:$port" \
    --max-examples "${ST_MAX_EXAMPLES:-15}" \
    --suppress-health-check=filter_too_much \
    --workers 1
}

run_st auth "$AUTH_PORT"
run_st transactions "$TXN_PORT"

echo "Schemathesis OK en ambos servicios."
