"""
Nidhi TEST settings — used ONLY by pytest (pytest.ini sets
DJANGO_SETTINGS_MODULE = nidhi_backend.test_settings).

Safety (TESTING_STRATEGY #13):
  * DEBUG=False, dummy SECRET_KEY, locmem email backend.
  * REST_FRAMEWORK.DEFAULT_AUTHENTICATION_CLASSES = [] so NO test ever hits the
    live Rubix IdP (api/authentication.py does a real `requests.post`).
    Tests authenticate via DRF force_authenticate instead.
  * The ORM test database is a THROWAWAY Postgres on port 5442 (CI service
    container / local docker). It is NEVER the real nidhi-db (5433) or
    nidhi-main_db (5435).
  * Provisioning tasks connect to NO real server because tests mock
    psycopg2.connect entirely (see backend/tests/test_provisioning.py).
"""
import os

from nidhi_backend.settings import *  # noqa: F401,F403

DEBUG = False
SECRET_KEY = os.environ.get("SECRET_KEY", "test-secret-key-not-for-prod")
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Throwaway test Postgres (CI service container maps 5442:5432; local docker too).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("NIDHI_TEST_DB_NAME", "nidhi_test"),
        "USER": os.environ.get("NIDHI_TEST_DB_USER", "postgres"),
        "PASSWORD": os.environ.get("NIDHI_TEST_DB_PASSWORD", "postgres"),
        "HOST": os.environ.get("NIDHI_TEST_DB_HOST", "localhost"),
        "PORT": os.environ.get("NIDHI_TEST_DB_PORT", "5442"),
    }
}

# TESTING_STRATEGY #13: never call the live Rubix IdP introspection endpoint.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
}

# Celery: run tasks synchronously during tests (no broker / worker needed).
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL

# Make 100% sure no real Telegram alert can fire during tests.
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""
