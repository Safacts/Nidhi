# MinIO Bucket Architecture

## Bucket Sizes (as of 2026-07-18)

### Production (on VPS MinIO - 72.60.218.127:9000)
| Bucket | Objects | Size |
|--------|---------|------|
| aacharya-production-media | 0 | 0 MB |
| abhyas-production-media | 614 | 224 MB |
| granth-production-media | 34,847 | 1,486 MB |
| new-nova-production-media | 94 | 435 MB |
| rubixdocs-production-media | 0 | 0 MB |
| vitharn-production-media | 0 | 0 MB |
| **Total** | **35,555** | **2.10 GB** |

### Development (on devserver MinIO - 100.83.65.7:9000)
| Bucket | Objects | Size |
|--------|---------|------|
| aacharya-development-media | 0 | 0 MB |
| abhyas-development-media | 614 | 224 MB |
| granth-development-media | 34,847 | 1,486 MB |
| new-nova-development-media | 2 | 0 MB |
| vitharn-development-media | 0 | 0 MB |
| **Total** | **35,463** | **1.71 GB** |

## Architecture: Prod-for-Prod (permanent)
- Production buckets are created on VPS MinIO (72.60.218.127:9000)
- Dev buckets are created on devserver MinIO (100.83.65.7:9000)
- Enforced in auto-provision code (api/views.py:189-195)
- Environment check: `if environment == 'production':` -> VPS, else -> devserver

## Backup Chain
1. **Primary**: VPS MinIO (nidhi_production_minio_data volume)
2. **Off-server backup**: Devserver TB hard disk (/mnt/Storage/backups/minio/) = 1.3 GB
3. **Schedule**: Cron on devserver, daily at 2 AM
4. **Script**: /mnt/Storage/backups/pull_minio_backup.sh (mc mirror, incremental)

## Key Files
- VPS MinIO compose: /services/nidhi-platform/docker-compose.minio.yml
- Backup pull script: /mnt/Storage/backups/pull_minio_backup.sh
- Auto-provision bucket logic: /home/rubix/workspace/Nidhi/backend/api/views.py lines 189-195
- Media gateway MinIO client: /home/rubix/workspace/Nidhi/backend/api/views.py lines 596-603
