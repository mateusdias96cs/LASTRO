#!/usr/bin/env bash
# Instala o Docker Engine (docker-ce) nativo no WSL2 / Ubuntu 26.04 "resolute".
# Idempotente: pode rodar de novo sem quebrar nada.
#
# Uso:  bash instalar-docker.sh          (pede a senha do sudo uma vez)
set -euo pipefail

TARGET_USER="${SUDO_USER:-$(id -un)}"
. /etc/os-release
CODENAME="${UBUNTU_CODENAME:-$VERSION_CODENAME}"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

say "Autenticando no sudo (senha pedida uma única vez)"
sudo -v

# Mantém o ticket do sudo vivo enquanto o script roda.
while true; do sudo -n true; sleep 50; kill -0 "$$" 2>/dev/null || exit; done 2>/dev/null &
SUDO_KEEPALIVE=$!
trap 'kill "$SUDO_KEEPALIVE" 2>/dev/null || true' EXIT

say "1/7 Removendo pacotes conflitantes do repo do Ubuntu"
for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
  sudo apt-get remove -y "$pkg" >/dev/null 2>&1 || true
done

say "2/7 Instalando pré-requisitos"
sudo apt-get update -qq
sudo apt-get install -y -qq ca-certificates curl

say "3/7 Adicionando a chave GPG oficial do Docker"
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

say "4/7 Registrando o repositório (dist: $CODENAME)"
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $CODENAME stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update -qq

say "5/7 Instalando docker-ce + buildx + compose"
sudo apt-get install -y \
  docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

say "6/7 Habilitando o serviço (systemd)"
sudo systemctl enable --now docker
sudo systemctl is-active docker

say "7/7 Liberando o docker sem sudo para o usuário '$TARGET_USER'"
sudo groupadd -f docker
sudo usermod -aG docker "$TARGET_USER"

say "Verificação (via sudo, pois o novo grupo ainda não vale nesta sessão)"
sudo docker version --format 'Client {{.Client.Version}} / Server {{.Server.Version}}'
sudo docker run --rm hello-world >/dev/null && echo "hello-world: OK"
sudo docker buildx version
sudo docker compose version

printf '\n\033[1;32mDocker instalado.\033[0m\n'
cat <<EOF

FALTA UM PASSO — o grupo 'docker' só passa a valer numa sessão nova.
No PowerShell/CMD do Windows, rode:

    wsl --shutdown

Depois reabra o WSL (e o Claude Code). Aí 'docker ps' funciona sem sudo.
EOF
