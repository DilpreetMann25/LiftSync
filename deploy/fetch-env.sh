#!/usr/bin/env bash
#
# Pull every parameter under /liftsync/ from SSM Parameter Store and
# write them as KEY=VALUE lines to the file systemd hands to the app.
#
# Credentials come from the EC2 instance's IAM role, so there are no
# AWS keys anywhere on the server. Parameter Store stays the single
# source of truth; this file is regenerated on every deploy, so a
# secret rotated in AWS reaches the app on the next deploy.
#
# Usage (as root): bash /opt/liftsync/app/deploy/fetch-env.sh

set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
PREFIX=/liftsync
OUT=/etc/liftsync/liftsync.env

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT   # never leave a copy of the secrets lying around

aws ssm get-parameters-by-path \
    --path "$PREFIX" \
    --with-decryption \
    --region "$REGION" \
    --query "Parameters[].[Name,Value]" \
    --output text \
  | while IFS=$'\t' read -r name value; do
      # /liftsync/DATABASE_URL  ->  DATABASE_URL=...
      printf '%s=%s\n' "${name##*/}" "$value"
    done > "$TMP"

# Fail loudly now rather than starting an app that will crash later.
for key in DATABASE_URL JWT_SECRET_KEY ENVIRONMENT; do
  if ! grep -q "^${key}=" "$TMP"; then
    echo "ERROR: $PREFIX/$key is missing from Parameter Store" >&2
    exit 1
  fi
done

# 640 root:liftsync -> root can write it, the app can read it, nobody
# else can see it. `install` sets mode and owner atomically, so there
# is no moment where the file exists with looser permissions.
install -m 640 -o root -g liftsync "$TMP" "$OUT"

# Print the variable NAMES only. Never echo secret values into logs.
echo "Wrote $(wc -l < "$OUT") variables to $OUT: $(cut -d= -f1 "$OUT" | tr '\n' ' ')"
