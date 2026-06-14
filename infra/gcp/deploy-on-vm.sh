#!/usr/bin/env bash
# Despliega/actualiza la consola EN LA VM. Clona/actualiza el repo, genera las claves
# RS256, levanta el stack de producción (edge + Caddy/TLS + datastores cerrados) y siembra.
# Requiere: Docker, y DOMAIN exportado (el subdominio DuckDNS que resuelve a esta VM).
#
# Uso en la VM:   DOMAIN=tu-sub.duckdns.org bash deploy-on-vm.sh
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/faborubio/consola-transaccional.git}"
REPO_DIR="${REPO_DIR:-$HOME/consola}"
SEED_COUNT="${SEED_COUNT:-500000}"
: "${DOMAIN:?export DOMAIN=tu-sub.duckdns.org (debe resolver a la IP de esta VM)}"

# 1. Código
if [[ -d "$REPO_DIR/.git" ]]; then
  git -C "$REPO_DIR" pull --ff-only
else
  git clone "$REPO_URL" "$REPO_DIR"
fi
cd "$REPO_DIR/infra"

# 2. Claves RS256 (auth firma, transactions verifica; nunca en git)
if [[ ! -f keys/jwt-private.pem ]]; then
  mkdir -p keys
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out keys/jwt-private.pem
  openssl pkey -in keys/jwt-private.pem -pubout -out keys/jwt-public.pem
fi

# 3. Stack de producción. `env UID/GID`: auth corre con ese uid para leer la clave 0600
#    montada (problemas-resueltos #18). DOMAIN va al Caddyfile para el cert TLS.
COMPOSE=(-f docker-compose.yml -f docker-compose.edge.yml -f docker-compose.prod.yml)
env "UID=$(id -u)" "GID=$(id -g)" "DOMAIN=$DOMAIN" docker compose "${COMPOSE[@]}" up -d --build

# 4. Esperar a que el API responda (mongo RS + apps listos) y sembrar 500k
echo "Esperando al API…"
for _ in $(seq 1 60); do
  docker compose "${COMPOSE[@]}" exec -T transactions \
    python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')" 2>/dev/null && break
  sleep 3
done

# El Caddyfile es un bind-mount → `up` no recrea Caddy; recargar para aplicar cambios
# (headers de seguridad, dominio). Inofensivo en el primer deploy.
docker compose "${COMPOSE[@]}" exec -T caddy caddy reload --config /etc/caddy/Caddyfile 2>/dev/null || true

# Sembrar SOLO si la base está vacía: así un redeploy (o el CD) no borra los datos ni
# paga 500k inserts cada vez. El cron de abajo se encarga de refrescar la demo.
COUNT=$(docker compose "${COMPOSE[@]}" exec -T mongo \
  mongosh --quiet --eval 'db.getSiblingDB("transactions_db").transactions.estimatedDocumentCount()' \
  2>/dev/null | tr -dc '0-9' || true)
if [[ "${COUNT:-0}" -lt 1 ]]; then
  echo "Base vacía → sembrando $SEED_COUNT…"
  SEED_COUNT="$SEED_COUNT" REPO_DIR="$REPO_DIR" bash gcp/reseed.sh
else
  echo "Ya hay $COUNT transacciones; no se re-siembra (idempotente)."
fi

# 5. Cron de reseed (idempotente): re-siembra cada 6h para datos demo limpios.
if ! crontab -l 2>/dev/null | grep -qF "gcp/reseed.sh"; then
  (crontab -l 2>/dev/null
   echo "0 */6 * * * SEED_COUNT=$SEED_COUNT REPO_DIR=$REPO_DIR bash $REPO_DIR/infra/gcp/reseed.sh >> \$HOME/reseed.log 2>&1") | crontab -
  echo "Cron de reseed instalado (cada 6h)."
fi

cat <<EOF

✅ Demo desplegada: https://$DOMAIN  (login: supervisor1 / Demo1234!)
   Caddy provisiona el cert TLS al primer acceso (unos segundos).
EOF
