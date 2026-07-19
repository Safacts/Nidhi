# Disaster Recovery Plan

## Architecture (Current State)

| Component | Location | Devserver Down | VPS Down |
|-----------|----------|---------------|----------|
| Nidhi API | devserver | Unavailable | Unaffected |
| Dev MinIO | devserver | Unavailable | Unaffected |
| Production MinIO | VPS (nidhi-production-minio) | Still running | Unavailable |
| Production DBs | VPS (nidhi-live-data-plane:5435) | Still running | Unavailable |
| App containers | VPS | Still running | Unavailable |

## Key Facts

### Bucket Sizes (as of 2026-07-18)
- **Production (VPS)**: 35,555 objects, 2.10 GB
- **Development (devserver)**: 35,463 objects, 1.71 GB

### Auto-Backup (DBs)
- **Schedule**: Daily at midnight via Celery beat
- **Mechanism**: `backup_all_databases` iterates ALL active instances
- **Coverage**: NEW DBs are automatically picked up on next midnight cycle
- **Storage**: Encrypted `.dump.enc` on persistent volume + Telegram off-site
- **Monitoring**: API at `/api/backups/` + AdminDashboard Backups tab in Nidhi UI

### Auto-Backup (MinIO)
- **Schedule**: Daily at 2 AM via devserver cron
- **Mechanism**: `mc mirror` pulls from VPS MinIO to devserver TB hard disk
- **Coverage**: NEW buckets automatically captured (mc mirrors all)
- **Storage**: `/mnt/Storage/backups/minio/` (869 GB free)
- **Monitoring**: NOT in Nidhi UI (cron-only)

### Auto-Provision (Prod-for-Prod)
- Production environment -> bucket on VPS MinIO (72.60.218.127:9000)
- Development environment -> bucket on devserver MinIO (100.83.65.7:9000)
- Unknown/future environments -> devserver MinIO (safe default)
- Enforced in `api/views.py:189-197` and `api/tasks.py:730-742`

## DR Scenarios

### 1. Devserver Down
- **Production DBs**: Working (on VPS, apps connect directly)
- **Production MinIO**: Working (on VPS, apps have cached credentials)
- **Media Gateway**: DOWN (on devserver) — apps use direct MinIO credentials
- **Auto-provision**: DOWN — new deployments can't get credentials
- **Nidhi UI**: DOWN
- **Backups**: DB backup schedule paused, MinIO backup cron paused

**Mitigation**:
- Apps that cache credentials survive container rebuilds
- For new deployments: manually inject credentials via env vars
- Nidhi recovery: clone repo, run `docker compose up` on any machine; point to existing DBs + MinIO

### 2. VPS Down
- **Everything production**: DOWN
- **Dev environments**: Working (devserver independent)

**Recovery**:
1. Restore DBs from standby (`nidhi-live-data-standby` on separate VPS volume)
2. Restore MinIO from devserver backup (`/mnt/Storage/backups/minio/`)
3. Redeploy app containers from GHCR

### 3. App Container Rebuilding During Devserver Downtime
- Apps use cached credentials from auto-provision (stored in Docker env or .env files)
- If credentials are lost during rebuild: CANNOT auto-provision (devserver down)
- **Workaround**: Inject cached creds manually, or keep a `.env.backup` on VPS

## Gaps & Recommendations

### Gap 1: MinIO backup not in Nidhi UI
The Nidhi AdminDashboard has a Backups tab (for DBs) but NO MinIO backup monitoring.
**Fix**: Add MinIO backup status to the API and UI.

### Gap 2: No internal data transfer mechanism (SCRUM-661)
Nidhi has `replicate_to_dev` (DB replication) and `relocate_bucket` (bucket endpoint change) but no generic data transfer between servers.
**Fix**: SCRUM-661 tracks this feature.

### Gap 3: Devserver single point of failure for control plane
If devserver is down, auto-provision, media gateway, and Nidhi UI are unavailable.
**Fix**: Consider a Nidhi standby container that can be quickly spun up on another machine.

## Files
- VPS MinIO compose: `/services/nidhi-platform/docker-compose.minio.yml`
- Backup pull script: `/mnt/Storage/backups/pull_minio_backup.sh`
- Auto-provision bucket logic: `/home/rubix/workspace/Nidhi/backend/api/views.py:189-197`
- Provision bucket task: `/home/rubix/workspace/Nidhi/backend/api/tasks.py:730-742`
- Media gateway: `/home/rubix/workspace/Nidhi/backend/api/views.py:608-670`
- Backup views: `/home/rubix/workspace/Nidhi/backend/api/views.py:545-615`
- Celery beat schedule: `/home/rubix/workspace/Nidhi/backend/nidhi_backend/celery.py:20-50`
- Nidhi frontend AdminDashboard: `/home/rubix/workspace/Nidhi/frontend/src/pages/AdminDashboard.jsx`
