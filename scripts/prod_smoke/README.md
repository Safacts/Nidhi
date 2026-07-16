# Nidhi Production Smoke-Test + Auto-Rollback (SCRUM-593 / TESTING_STRATEGY #13)

Adapted from New-Nova's `scripts/prod_smoke/` for the **Nidhi DBaaS control
plane**. Nidhi is an *internal* service, so the smoke checks are tuned to its
reality: a path-prefixed SPA (`/nidhi`) and a provisioning-aware heartbeat
endpoint.

## Files

| File | Runs on | Purpose |
|------|---------|---------|
| `smoke_nidhi.py` | any host (hits public URL) | Labeled HTTP smoke checks; exit 0 = pass. |
| `rollback_nidhi.sh` | **VPS** (`72.60.218.127`) | Pins compose to `:lastgood` and recreates `nidhi-backend`. |
| `record_lastgood_nidhi.sh` | **VPS** | Tags the running backend image as last-good (after a PASS). |
| `postdeploy_check_nidhi.sh` | **VPS** (best) / dev server (smoke-only) | Orchestrator: settle → smoke → record or rollback + alert. |

## Smoke checks (stdlib only)

1. `landing_page` — `GET {base}/` → 200 and the SPA marker `id="root"`.
   Default base: `https://rubix.tail2d2f35.ts.net/nidhi` (override `NIDHI_BASE_URL`).
2. `backend_heartbeat` — `POST {base}/api/heartbeat/` → 200. This endpoint is
   auth + provisioning-aware, so it needs the shared secret and a real
   provisioned app slug:
   - `NIDHI_APP_API_KEY` — shared secret (Bearer). If **unset**, the check is
     SKIPPED (warning) rather than failing.
   - `NIDHI_SMOKE_PROJECT` (default `nidhi`) and `NIDHI_SMOKE_ENV`
     (default `production`) identify the provisioned app.
   - 200 → full pass. 401/403/404 → backend is up but no matching instance
     (config, not outage) → still PASS with a warning. 5xx / connection error →
     real FAIL.

## Image / compose (verified facts)

- Backend image: `aadisheshu/nidhi_backend:latest` (per `.github/workflows/deploy.yml`).
- VPS compose: `/services/nidhi-platform/docker-compose.yml`, service `nidhi-backend`.
- Backend listen port: `8000` (container) → `8001` on the VPS host (per the repo's `docker-compose.yml`).
- Nidhi is **internal** — no public domain. Smoke/rollback still alert via email
  (`_AI_AGENTS/send_report.py`) and optionally the Nirikshan dashboard webhook
  (`NIRIKSHAN_URL`, best-effort, never blocking).

## Rollback strategy — local `:lastgood` tag (VPS reality)

Same as New-Nova: the running image is pulled as `:latest` with empty
RepoDigests, so `record_lastgood_nidhi.sh` points a local `:lastgood` tag at the
verified image ID (protecting it from prune/Watchtower). `rollback_nidhi.sh`
pins the compose image line to `:lastgood` and recreates the service; because
`:lastgood` isn't in the registry, Watchtower won't undo the rollback. Repoint
to `:latest` after a verified fix.

## Usage

```bash
# Smoke only (any host):
python3 smoke_nidhi.py --url https://rubix.tail2d2f35.ts.net/nidhi

# After a verified-good deploy, on the VPS:
bash record_lastgood_nidhi.sh

# Manual rollback on the VPS:
bash rollback_nidhi.sh

# Orchestrated check (schedule after Watchtower deploys):
bash postdeploy_check_nidhi.sh
```

## Scheduling on the VPS

`/etc/systemd/system/nidhi-postdeploy.service`:
```ini
[Unit]
Description=Nidhi post-deploy smoke + rollback
After=docker.service

[Service]
Type=oneshot
Environment=NIDHI_BASE_URL=https://rubix.tail2d2f35.ts.net/nidhi
Environment=ALERT_HELPER=/opt/nidhi/send_report.py
Environment=NIDHI_APP_API_KEY=<shared-secret>
ExecStart=/opt/nidhi/postdeploy_check_nidhi.sh
```
`/etc/systemd/system/nidhi-postdeploy.timer`:
```ini
[Timer]
OnCalendar=*:00/5
Persistent=true

[Install]
WantedBy=timers.target
```
Then `systemctl enable --now nidhi-postdeploy.timer`.
