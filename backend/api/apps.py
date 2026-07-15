from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'

    def ready(self):
        import os
        import sys
        # Only start the monitor in the main web server process (avoid running in migrations or multiple times in runserver)
        if 'runserver' not in sys.argv and 'migrate' not in sys.argv and 'makemigrations' not in sys.argv:
            # For gunicorn or uwsgi, this runs once per worker. 
            # In a small setup, 1 worker is fine. If multiple, they all poll (lightweight).
            from .monitor import start_monitoring_thread
            start_monitoring_thread()
        elif os.environ.get('RUN_MAIN', None) == 'true':
            # runserver reload process
            from .monitor import start_monitoring_thread
            start_monitoring_thread()
