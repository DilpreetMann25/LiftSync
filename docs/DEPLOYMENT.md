# Deployment — AWS

Region: **us-east-1** (N. Virginia). Every resource carries the tag **`project = Liftsync`** (tags are case-sensitive — keep the spelling identical).

**Live:** https://44-215-19-13.sslip.io — demo login `demo@liftsync.app` / `liftsync-demo-2026`

Funded by AWS credits that **expire 17 March 2027**. Tear everything down in early March, before real billing starts.

---

## Architecture

```
                 internet
                    │  80 / 443
                    ▼
   ┌──────────── default VPC ────────────────────────┐
   │                                                 │
   │   EC2  (liftsync-ec2-sg)                        │
   │   Nginx ──▶ static React build                  │
   │         └─▶ /api → uvicorn (FastAPI, systemd)   │
   │                    │                            │
   │                    │ 5432, only from the EC2 SG │
   │                    ▼                            │
   │   RDS PostgreSQL 16 (liftsync-rds-sg)           │
   │   public access: OFF — no public IP at all      │
   └─────────────────────────────────────────────────┘
```

The database has no public IP. Its hostname resolves to a private `172.31.x.x` address, so nothing outside the VPC has a route to it — the security group is a second layer, not the only one.

---

## Resource inventory

| Resource | Name | Notes | Status |
| --- | --- | --- | --- |
| RDS PostgreSQL 16.15 | `liftsync-db` | db.t3.micro, 20 GiB gp2, single-AZ, public access off, us-east-1b, 1-day backups | ✅ created 2026-10-05 |
| Security group | `liftsync-rds-sg` | Single inbound rule: **5432 from `liftsync-ec2-sg`** | ✅ locked down 2026-10-05 |
| EC2 instance | `liftsync-api` | t4g.micro (Arm), Ubuntu 24.04, 10 GiB gp3 encrypted, CPU credits **Standard** | ✅ created 2026-10-05 |
| Security group | `liftsync-ec2-sg` | 22 from home IP; 80 and 443 from anywhere | ✅ created 2026-10-05 |
| Key pair | `liftsync-key` | ED25519, `~/.ssh/liftsync-key.pem`, mode 400, never committed | ✅ created 2026-10-05 |
| Elastic IP | `liftsync-eip` | `44.215.19.13`, attached to `liftsync-api`. **Bills even when unattached — release at teardown.** | ✅ 2026-10-06 |
| TLS certificate | Let's Encrypt | `44-215-19-13.sslip.io`; webroot, auto-renewed by `certbot.timer`, reloads Nginx via deploy hook | ✅ 2026-10-06 |
| IAM role | `liftsync-ec2-role` | `AmazonSSMManagedInstanceCore` + inline `liftsync-read-parameters` (Get* on `/liftsync/*` only). Attached to `liftsync-api`. | ✅ verified 2026-10-06 |
| OIDC identity provider | `token.actions.githubusercontent.com` | Lets AWS verify tokens signed by GitHub Actions | ⬜ |
| IAM role | `liftsync-github-deploy` | Trust: only `repo:DilpreetMann25/LiftSync:ref:refs/heads/main`. Inline `liftsync-run-deploy`: `ssm:SendCommand` on `liftsync-api` only | ⬜ |
| SSM parameters | `/liftsync/*` | SecureString: `DATABASE_URL`, `JWT_SECRET_KEY`, `GEMINI_API_KEY` · String: `ENVIRONMENT`, `LLM_PROVIDER`, `AI_MODEL`, `DOMAIN` · Standard tier, `alias/aws/ssm` | ✅ created 2026-10-05 |

The RDS master password lives in the Passwords app, not in this repo. If lost, reset it via RDS → Modify.

**SSH:** `ssh -i ~/.ssh/liftsync-key.pem ubuntu@44.215.19.13`. The Elastic IP survives stops and starts. If SSH times out, check the instance is running and that your home IP still matches the port-22 rule — home IPs change.

**Verified 2026-10-05:** from the EC2 box, `nc -zv <rds-endpoint> 5432` succeeds (the endpoint resolves to a private 172.31.x.x address). From a laptop, the same endpoint has no route — public access is genuinely off.

---

## Deploying

Everything the server needs is scripted in [`deploy/`](../deploy):

| File | Runs | Does |
| --- | --- | --- |
| `bootstrap.sh` | once per server | Packages, Node 22, swap, the `liftsync` system user, directories, RDS cert, clone |
| `deploy.sh` | every deploy | Pull `main`, install deps, fetch secrets, migrate, build frontend, restart, health check |
| `fetch-env.sh` | called by `deploy.sh` | Parameter Store → `/etc/liftsync/liftsync.env` (mode 640) |
| `liftsync.service` | systemd | Runs uvicorn on 127.0.0.1:8000 as `liftsync`, restarts on crash |
| `nginx-locations.conf` | Nginx | Shared routes: React build, `/api` and `/docs` proxied to uvicorn |
| `nginx-liftsync.conf` | Nginx | HTTP-only site, used until a certificate exists |
| `nginx-liftsync-https.conf.template` | Nginx | HTTPS site; `deploy.sh` fills in `${DOMAIN}` and uses it once the certificate exists |

**Fresh server:**

```bash
curl -fsSL https://raw.githubusercontent.com/DilpreetMann25/LiftSync/main/deploy/bootstrap.sh | sudo bash
sudo bash /opt/liftsync/app/deploy/deploy.sh
```

**Every deploy after that:** `sudo bash /opt/liftsync/app/deploy/deploy.sh`

**First production deploy: 2026-10-06**, commit `5b0ded3`. Migrations 0001–0003 applied to RDS; health check returned `{"status":"ok","database":"reachable","environment":"production"}`.

**Layout on the server:**

```
/opt/liftsync/app        git checkout — disposable, reset to origin/main on every deploy
/opt/liftsync/venv       Python environment (outside the checkout)
/etc/liftsync/           liftsync.env (secrets) + rds-global-bundle.pem
/var/www/liftsync/       built frontend, served by Nginx
```

**HTTPS (one-time, after `/liftsync/DOMAIN` is set and one deploy has run):**

```bash
sudo certbot certonly --webroot -w /var/www/certbot -d "$DOMAIN" \
  --register-unsafely-without-email --agree-tos \
  --deploy-hook "systemctl reload nginx"
sudo bash /opt/liftsync/app/deploy/deploy.sh   # now picks the HTTPS config
sudo certbot renew --dry-run                   # proves renewal will work
```

Certbot only places certificates in `/etc/letsencrypt`; it never edits Nginx config, so deploys can't undo HTTPS. Renewal runs twice a day via `certbot.timer`, and the deploy hook reloads Nginx when a new certificate lands.

**Day-to-day:**

```bash
sudo systemctl status liftsync        # is it running?
sudo journalctl -u liftsync -f        # live logs
sudo journalctl -u liftsync -n 100    # last 100 lines
```

---

## Approximate monthly cost

| Item | ≈ USD / month |
| --- | --- |
| RDS db.t3.micro | 13.00 |
| RDS storage, 20 GiB | 2.30 |
| EC2 t4g.micro | 6.00 |
| Public IPv4 address | 3.65 |
| EC2 disk, ~10 GiB | 0.80 |
| **Total** | **≈ 26** |

Check **Billing → Credits** every couple of weeks. While credits cover charges the bill can read $0, so the zero-spend budget alarm may stay quiet — it guards real money, not credit burn.

---

## Teardown checklist (early March 2027)

Order matters: things that depend on others go first.

1. **EC2** → terminate `liftsync-api`. Confirm its disk (EBS volume) is deleted too.
2. **Elastic IP** (if one was allocated) → release it. An unattached Elastic IP still bills.
3. **RDS** → delete `liftsync-db`.
   - Final snapshot: skip it, or take it and delete the snapshot afterwards (snapshots bill for storage).
   - **Uncheck "retain automated backups"**.
4. **Security groups** → delete `liftsync-ec2-sg` and `liftsync-rds-sg`.
5. **SSM Parameter Store** → delete everything under `/liftsync/`.
6. **IAM** → delete roles `liftsync-ec2-role` and `liftsync-github-deploy`, then **Identity providers** → delete `token.actions.githubusercontent.com`. Free, but a leftover trust relationship is a security liability. IAM is global, so the tag search in step 8 may not list these.
   Then on GitHub: remove the deploy job from `ci.yml` (or it fails on every push) and delete the three Actions variables.
7. **EC2 → Key pairs** → delete `liftsync-key`.
8. **Resource Groups → Tag Editor** → search `project = Liftsync` in us-east-1. Expect zero results.
9. Next day: **Billing → Bills** forecast should be $0.00.
