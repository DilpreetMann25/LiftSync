#!/usr/bin/env bash
#
# One-time setup for a fresh Ubuntu 24.04 server.
#
# Safe to re-run: every step checks whether it has already been done.
# That property is called idempotence, and it is what lets you rebuild
# the whole server from nothing with one command if it ever dies.
#
# Usage (on the server):
#   curl -fsSL https://raw.githubusercontent.com/DilpreetMann25/LiftSync/main/deploy/bootstrap.sh | sudo bash
#
# Then deploy with:
#   sudo bash /opt/liftsync/app/deploy/deploy.sh

set -euo pipefail
# -e  stop at the first command that fails
# -u  treat an unset variable as an error instead of an empty string
# -o pipefail  a pipeline fails if ANY part fails, not just the last

REPO_URL="${REPO_URL:-https://github.com/DilpreetMann25/LiftSync.git}"
APP_USER=liftsync
APP_HOME=/opt/liftsync
APP_DIR=$APP_HOME/app

log() { printf '\n==> %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "Run as root: sudo bash $0" >&2; exit 1; }

log "System packages"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  python3-venv git nginx postgresql-client rsync curl

log "Node.js 22"
# Ubuntu 24.04's own nodejs package is v18, which is too old for
# Tailwind v4. NodeSource publishes current releases for Ubuntu.
if ! command -v node >/dev/null \
   || [ "$(node -p 'process.versions.node.split(".")[0]')" -lt 20 ]; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nodejs
fi
echo "node $(node --version), npm $(npm --version)"

log "AWS CLI"
command -v aws >/dev/null || snap install aws-cli --classic

log "Swap (2 GB)"
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
fi
grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab

log "App user"
# A dedicated system account with no password and no login shell.
# The API runs as this user, so if the app were ever compromised the
# attacker gets an account that cannot log in, cannot sudo, and can
# only write to /opt/liftsync.
id "$APP_USER" >/dev/null 2>&1 || useradd \
  --system --create-home --home-dir "$APP_HOME" \
  --shell /usr/sbin/nologin "$APP_USER"

log "Directories"
# /etc/liftsync holds config and the secrets file; only root and the
# app user can enter it.
install -d -m 750 -o root -g "$APP_USER" /etc/liftsync
# Nginx serves the built frontend from here.
install -d -m 755 /var/www/liftsync

log "RDS certificate bundle"
if [ ! -f /etc/liftsync/rds-global-bundle.pem ]; then
  curl -fsSL -o /etc/liftsync/rds-global-bundle.pem \
    https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem
fi
chmod 644 /etc/liftsync/rds-global-bundle.pem

log "Code"
if [ ! -d "$APP_DIR/.git" ]; then
  sudo -u "$APP_USER" -H git clone --quiet "$REPO_URL" "$APP_DIR"
fi

log "Nginx: remove the default welcome page"
rm -f /etc/nginx/sites-enabled/default

log "Bootstrap complete. Next: sudo bash $APP_DIR/deploy/deploy.sh"
