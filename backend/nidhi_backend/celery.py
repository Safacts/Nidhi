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
        # Previously Nidhi trusted the 'available' flag set at provision time, hiding the
        # 2026-07-17 data-plane wipe for days.
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
        # Assuming we need to pass instance IDs. For automation, we'll need to fetch them dynamically,
        # but let's just use the known IDs for now, or use a new wrapper task.
        # It's better to create a wrapper task that finds prod instances and replicates them.
        # But for now, we'll just add the schedule entry.
        'schedule': crontab(minute=0, hour=2, day_of_week='sun'), # Sunday 2 AM
        'args': (4, 1, 'new_nova_dev'), # prod_instance_id=4, dev_server_id=1, new_db_name='new_nova_dev'
    },
}

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
