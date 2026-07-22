import os
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nidhi_backend.settings')

app = Celery('nidhi_backend')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Set up periodic tasks
app.conf.beat_schedule = {
    'backup-all-databases-every-midnight': {
        'task': 'api.tasks.backup_all_databases',
        'schedule': crontab(minute=0, hour=0), # Midnight every day
    },
    'refresh-delayed-replicas-daily': {
        # SCRUM-250: maintain a ~24h-behind delayed replica of every active DB.
        'task': 'api.tasks.refresh_delayed_replicas',
        'schedule': crontab(minute=0, hour=1),  # 01:00 every day
    },
    'verify-database-liveness-hourly': {
        # SCRUM data-safety: actively confirm each provisioned DB still exists/connects.
        'task': 'api.tasks.verify_database_liveness',
        'schedule': crontab(minute=30),  # every hour at :30
    },
    'check-stale-heartbeats-hourly': {
        # SCRUM-260: alert on instances that stopped reporting a heartbeat.
        'task': 'api.tasks.check_stale_heartbeats',
        'schedule': crontab(minute=15),  # every hour at :15
    },
    'replicate-new-nova-prod-to-dev-weekly': {
        'task': 'api.tasks.replicate_prod_to_dev',
        'schedule': crontab(minute=0, hour=2, day_of_week='sun'), # Sunday 2 AM
        'args': (4, 1, 'new_nova_dev'),
    },
    'check-minio-health-every-5-min': {
        'task': 'api.tasks.check_minio_health',
        'schedule': crontab(minute='*/5'),  # Every 5 minutes
    },
    'send-ai-alert-summary-every-30-min': {
        'task': 'api.tasks.send_ai_alert_summary',
        'schedule': crontab(minute='*/30'),  # Every 30 minutes
    },
    # Continuous backup watchdog — alerts if a backup run is stale/failed/missing
    'monitor-backup-health-hourly': {
        'task': 'api.tasks.monitor_backup_health',
        'schedule': crontab(minute=45),  # every hour at :45
    },
    # Deploy-drift watchdog — alerts if a published :latest is never confirmed
    # deployed (Watchtower stalled / ghcr auth fail on VPS). Nidhi is internal;
    # this task only observes ghcr, never deploys.
    'verify-deploy-drift-hourly': {
        'task': 'api.tasks.verify_deploy_drift',
        'schedule': crontab(minute=20),  # every hour at :20
    },
    # --- Nidhi-managed backup control plane (replaces host cron) ---
    'backup-minio-media-nightly': {
        # Mirror all prod MinIO buckets to devserver TB disk. Runs after DB dumps.
        'task': 'api.tasks.backup_all_minio_media',
        'schedule': crontab(minute=30, hour=2),  # 02:30 every day
    },
    'replicate-buckets-nightly': {
        # Bucket->bucket media replication (MinIO->MinIO), mirroring the DB-to-DB
        # replicate_prod_to_dev pattern. Replicates every available bucket to its
        # prod<->dev counterpart. Runs after the TB-disk mirror.
        'task': 'api.tasks.replicate_all_buckets',
        'schedule': crontab(minute=0, hour=3),  # 03:00 every day
    },
    'copy-db-backups-to-tb-disk-nightly': {
        # Copy encrypted DB dumps (volume) to durable TB disk copy.
        'task': 'api.tasks.copy_db_backups_to_tb_disk',
        'schedule': crontab(minute=15, hour=0),  # 00:15 every day (after midnight DB dump)
    },
}

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
