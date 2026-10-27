#!/bin/sh
# Turns a fresh Ubuntu 24.04 VPS into the running Kith stack (ADR-0021). It
# knows nothing about the provider: it needs only an address and SSH access
# as root, through your ssh-agent or ~/.ssh (the host must already be in
# known_hosts). Safe to run again on a VPS it has set up. Run from the repo root:
#   GHCR_USER=<github user> GHCR_TOKEN=<read:packages token> \
#     sh infra/loadtest/setup.sh root@<address> <image tag> <env file>
# <env file> becomes /opt/kith/.env (docs/deploy-quickstart.md, step 4). The
# stack is the prod one: same compose file, Caddyfile and deploy.sh.
set -eu

if [ $# -ne 3 ]; then
  echo "usage: setup.sh <user>@<address> <image tag> <env file>" >&2
  exit 1
fi
target=$1 image_tag=$2 env_file=$3
case "$image_tag" in
  *[!A-Za-z0-9_.-]*) echo "setup: '$image_tag' is not an image tag" >&2; exit 1 ;;
esac
: "${GHCR_USER:?set GHCR_USER}" "${GHCR_TOKEN:?set GHCR_TOKEN}"
address=${target#*@}

# Windows line endings (a copy through the Windows clipboard) would end up in
# every value, so they are stripped. Compose would take the last DOMAIN line.
env=$(tr -d '\r' < "$env_file")
domain=$(echo "$env" | sed -n 's/^DOMAIN=//p' | tail -n1 | tr -d "\"'")
if [ -z "$domain" ]; then
  echo "setup: $env_file has no DOMAIN" >&2
  exit 1
fi
if ! ssh-keygen -F "$address" > /dev/null; then
  echo "setup: $address is not in ~/.ssh/known_hosts (docs/deploy-quickstart.md, \"Load-test VPS\")" >&2
  exit 1
fi

ssh_opts="-o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10"
# shellcheck disable=SC2086
as_root() { ssh $ssh_opts "$target" "$@"; }
# shellcheck disable=SC2086
as_deploy() { ssh $ssh_opts "deploy@$address" "$@"; }

# A VPS that was just installed may still be booting, or still be running
# its provider's first-boot steps.
echo "setup: waiting for SSH on $address"
for _ in $(seq 60); do
  as_root true 2> /dev/null && break
  sleep 5
done
as_root true

# Everything that needs root, as in docs/deploy-quickstart.md step 3. Root
# stays reachable with a key, so this script can run again.
echo "setup: preparing the server"
as_root sh -s << 'EOF'
set -eu
export DEBIAN_FRONTEND=noninteractive
apt_get() { apt-get -o DPkg::Lock::Timeout=300 "$@"; }

id deploy > /dev/null 2>&1 || adduser --disabled-password --gecos "" deploy
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
install -m 600 -o deploy -g deploy /root/.ssh/authorized_keys /home/deploy/.ssh/authorized_keys

ufw allow 22 > /dev/null && ufw allow 80 > /dev/null && ufw allow 443 > /dev/null
ufw --force enable

if ! docker compose version > /dev/null 2>&1; then
  apt_get update -q
  apt_get install -y -q ca-certificates curl
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt_get update -q
  apt_get install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
usermod -aG docker deploy

mkdir -p /etc/systemd/journald.conf.d
printf '[Journal]\nStorage=persistent\nSystemMaxUse=1G\n' > /etc/systemd/journald.conf.d/00-kith.conf
systemctl restart systemd-journald
daemon='{ "log-driver": "journald", "log-opts": { "labels": "com.docker.compose.service" } }'
if [ "$(cat /etc/docker/daemon.json 2> /dev/null)" != "$daemon" ]; then
  echo "$daemon" > /etc/docker/daemon.json
  systemctl restart docker
fi

echo 'vm.max_map_count=262144' > /etc/sysctl.d/99-opensearch.conf
sysctl -q --system

install -d -o deploy -g deploy /opt/kith

printf 'PasswordAuthentication no\nPermitRootLogin prohibit-password\n' > /etc/ssh/sshd_config.d/00-kith.conf
sshd -t && systemctl restart ssh
EOF

# The rest runs as deploy, as the deploy workflow does.
echo "setup: installing docker rollout and logging in to GHCR"
as_deploy sh -s << 'EOF'
set -eu
mkdir -p ~/.docker/cli-plugins
# The version CI's smoke test uses (.github/actions/smoke-test).
curl -fsSL https://raw.githubusercontent.com/wowu/docker-rollout/v0.14/docker-rollout -o ~/.docker/cli-plugins/docker-rollout
chmod +x ~/.docker/cli-plugins/docker-rollout
EOF
printf '%s' "$GHCR_TOKEN" | as_deploy docker login ghcr.io -u "$GHCR_USER" --password-stdin > /dev/null

echo "setup: copying the infra files and .env"
printf '%s\n' "$env" | as_deploy 'umask 077 && cat > /opt/kith/.env'
# shellcheck disable=SC2086
scp $ssh_opts -q infra/docker-compose.prod.yml infra/Caddyfile infra/pg-backup.sh infra/deploy.sh "deploy@$address:/opt/kith/"

echo "setup: deploying $image_tag"
as_deploy "cd /opt/kith && sh deploy.sh '$image_tag'"

# Through DNS and Caddy's real certificate, as a User reaches it.
echo "setup: checking https://$domain/health"
curl -fsS --retry 30 --retry-delay 5 --retry-all-errors "https://$domain/health"
echo
echo "setup: Kith is serving on https://$domain"
