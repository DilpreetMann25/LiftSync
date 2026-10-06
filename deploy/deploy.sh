#!/usr/bin/env bash
#
# Deploy the latest code on main. Idempotent: run it as often as you
# like. The same script runs by hand today and from GitHub Actions
# later, so the pipeline never does anything you have not seen work.
#
# Usage (on the server): sudo bash /opt/liftsync/app/deploy/deploy.sh

set -euo pipefail

APP_USER=liftsync
APP_DIR=/opt/liftsync/app
VENV=/opt/liftsync/venv
WEB_ROOT=/var/www/liftsync
ENV_FILE=/etc/liftsync/liftsync.env
BRANCH="${BRANCH:-main}"

log()    { printf '\n==> %s\n' "$*"; }
as_app() { sudo -u "$APP_USER" -H "$@"; }

[ "$(id -u)" -eq 0 ] || { echo "Run as root: sudo bash $0" >&2; exit 1; }

log "Code: origin/$BRANCH"
# reset --hard, not pull: the server's copy is disposable and must match
# GitHub exactly. Never edit code on the server -- it will be overwritten.
as_app git -C "$APP_DIR" fetch --quiet origin "$BRANCH"
as_app git -C "$APP_DIR" reset --quiet --hard "origin/$BRANCH"
echo "At commit: $(as_app git -C "$APP_DIR" log -1 --format='%h %s')"

log "Python dependencies"
# The venv lives OUTSIDE the git checkout, so reset --hard never touches it.
[ -x "$VENV/bin/python" ] || as_app python3 -m venv "$VENV"
as_app "$VENV/bin/pip" install --quiet --upgrade pip
as_app "$VENV/bin/pip" install --quiet -r "$APP_DIR/backend/requirements.txt"

log "Secrets from Parameter Store"
bash "$APP_DIR/deploy/fetch-env.sh"

log "Database migrations"
# systemd-run starts a one-off process with EXACTLY the same user and
# environment file the real service uses. Sourcing the env file in bash
# would break: DATABASE_URL contains '&', which bash treats as "run in
# the background". Letting systemd parse it guarantees migrations see
# the same values the app will.
systemd-run --quiet --wait --pipe --collect \
  --uid="$APP_USER" --gid="$APP_USER" \
  -p EnvironmentFile="$ENV_FILE" \
  -p WorkingDirectory="$APP_DIR/backend" \
  "$VENV/bin/alembic" upgrade head

log "Frontend build"
# npm ci (not npm install) installs exactly what package-lock.json says --
# the Node equivalent of pip install -r requirements.txt.
as_app bash -c "cd '$APP_DIR/frontend' && npm ci --no-audit --no-fund --loglevel=error && npm run build"
rsync -a --delete "$APP_DIR/frontend/dist/" "$WEB_ROOT/"

log "Service and Nginx config"
install -m 644 "$APP_DIR/deploy/liftsync.service" /etc/systemd/system/liftsync.service
install -m 644 "$APP_DIR/deploy/nginx-liftsync.conf" /etc/nginx/sites-available/liftsync
ln -sf /etc/nginx/sites-available/liftsync /etc/nginx/sites-enabled/liftsync
systemctl daemon-reload
systemctl enable --quiet liftsync
nginx -t   # refuses to continue if the Nginx config has a syntax error
systemctl reload-or-restart nginx

log "Restart API"
systemctl restart liftsync

log "Health check"
# Don't trust "systemctl restart" returning -- it only means the process
# launched. Ask the app itself, which runs SELECT 1 against RDS.
for _ in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:8000/api/v1/health >/dev/null 2>&1; then
    curl -fsS http://127.0.0.1:8000/api/v1/health; echo
    log "Deploy complete"
    exit 0
  fi
  sleep 2
done

echo "ERROR: API did not become healthy within 40s. Recent logs:" >&2
journalctl -u liftsync -n 60 --no-pager >&2
exit 1
