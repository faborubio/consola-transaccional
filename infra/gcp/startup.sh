#!/bin/bash
# Startup-script de la VM (Ubuntu 22.04): instala Docker Engine + compose plugin + git.
# Se pasa a `gcloud compute instances create --metadata-from-file=startup-script=...`.
set -e
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y ca-certificates curl git
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Que el usuario de login pueda usar docker sin sudo (toma efecto en la próxima sesión SSH).
for u in $(ls /home); do usermod -aG docker "$u" || true; done
systemctl enable --now docker
