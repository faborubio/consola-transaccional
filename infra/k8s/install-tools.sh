#!/usr/bin/env bash
# Instala kind y kubectl como binarios estáticos en ~/.local/bin (sin sudo, igual que
# node/uv/java en el entorno WSL). Usan el Docker que ya funciona.
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"

BIN="$HOME/.local/bin"
ARCH=amd64
KIND_VERSION=v0.24.0
mkdir -p "$BIN"

if ! command -v kubectl >/dev/null 2>&1; then
  KVER="$(curl -fsSL https://dl.k8s.io/release/stable.txt)"
  curl -fsSL "https://dl.k8s.io/release/${KVER}/bin/linux/${ARCH}/kubectl" -o "$BIN/kubectl"
  chmod +x "$BIN/kubectl"
  echo "kubectl ${KVER} → $BIN/kubectl"
else
  echo "kubectl ya presente: $(command -v kubectl)"
fi

if ! command -v kind >/dev/null 2>&1; then
  curl -fsSL "https://kind.sigs.k8s.io/dl/${KIND_VERSION}/kind-linux-${ARCH}" -o "$BIN/kind"
  chmod +x "$BIN/kind"
  echo "kind ${KIND_VERSION} → $BIN/kind"
else
  echo "kind ya presente: $(command -v kind)"
fi
