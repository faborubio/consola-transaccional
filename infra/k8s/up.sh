#!/usr/bin/env bash
# Construye las imágenes, crea el cluster kind, carga las imágenes, crea el Secret de
# claves RS256 (desde infra/keys, nunca de git) y despliega el stack completo.
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
CLUSTER=consola
KEYS="$ROOT/infra/keys"

command -v kind >/dev/null || { echo "Falta kind. Corre: make k8s-tools"; exit 1; }
command -v kubectl >/dev/null || { echo "Falta kubectl. Corre: make k8s-tools"; exit 1; }

# 1. Claves RS256 (fuera de git; solo auth monta la privada)
if [[ ! -f "$KEYS/jwt-private.pem" ]]; then
  mkdir -p "$KEYS"
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$KEYS/jwt-private.pem"
  openssl pkey -in "$KEYS/jwt-private.pem" -pubout -out "$KEYS/jwt-public.pem"
fi

# 2. Imágenes. `--provenance=false`: sin esto, buildkit emite un manifest list con
#    attestations y `kind load` (ctr import --all-platforms) se cuelga importándolas.
#    Edge: contexto raíz, necesita frontend/ + infra/gateway/nginx.conf.
echo "==> Construyendo imágenes…"
docker build --provenance=false -t consola-auth:local services/auth
docker build --provenance=false -t consola-transactions:local services/transactions
docker build --provenance=false -t consola-edge:local -f frontend/Dockerfile .

# 3. Cluster kind (idempotente) + carga de imágenes locales
kind get clusters | grep -qx "$CLUSTER" || kind create cluster --name "$CLUSTER"
echo "==> Cargando imágenes al cluster…"
# `kind load docker-image` pasa --all-platforms a `ctr import`, que se CUELGA con el
# containerd image store de Docker (índices OCI multi-plataforma). Import manual sin
# ese flag → importa solo la plataforma del host, al instante.
NODE="$(kind get nodes --name "$CLUSTER" | head -1)"
for img in consola-auth:local consola-transactions:local consola-edge:local; do
  docker save "$img" | docker exec -i "$NODE" ctr -n k8s.io images import --digests --snapshotter=overlayfs -
done

# 4. Namespace + Secret antes del resto (los pods montan el Secret al arrancar)
kubectl apply -f infra/k8s/namespace.yaml
kubectl -n consola delete secret jwt-keys --ignore-not-found
kubectl -n consola create secret generic jwt-keys \
  --from-file=jwt-private.pem="$KEYS/jwt-private.pem" \
  --from-file=jwt-public.pem="$KEYS/jwt-public.pem"

# 5. Stack completo
echo "==> kubectl apply -k infra/k8s"
kubectl apply -k infra/k8s

# 6. Readiness de la base ANTES de los apps con estado de arranque
kubectl -n consola rollout status statefulset/mongo --timeout=180s
kubectl -n consola wait --for=condition=complete job/mongo-init --timeout=180s

# El bootstrap de usuarios demo (auth) y los índices (transactions) corren una sola vez
# en el lifespan. Si esos pods arrancaron antes de que el RS fuera PRIMARY, ese trabajo
# se saltó silenciosamente (best-effort). Reiniciarlos ahora lo ejecuta contra la base
# lista → sin esto, el login demo falla (usuarios inexistentes).
kubectl -n consola rollout restart deploy/auth deploy/transactions

for d in redis auth transactions edge; do
  kubectl -n consola rollout status deploy/"$d" --timeout=180s
done

cat <<'EOF'

✅ Stack desplegado en el namespace `consola`.
   Abre la consola:
     kubectl -n consola port-forward svc/edge 8080:8080
   y navega a http://localhost:8080  (login demo: supervisor1 / Demo1234!)

   Seguir un correlation ID de punta a punta:
     kubectl -n consola logs deploy/edge
     kubectl -n consola logs deploy/transactions | grep <correlationId>
EOF
