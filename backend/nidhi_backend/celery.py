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
