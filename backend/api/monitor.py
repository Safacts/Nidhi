import logging

logger = logging.getLogger(__name__)

# SCRUM-260: The old 60s pg_stat_database polling loop has been removed.
#
# Rationale: counting `numbackends == 0` was a poor bypass signal (it also fires for idle apps)
# and violated the "no constant polling" design intent. Bypass detection is now event-driven:
#
#   * Apps POST a DATABASE_URL fingerprint to /api/heartbeat/ (see views.heartbeat). Nidhi
#     compares it to the provisioned instance and alerts on mismatch (SQLite/hardcoded fallback).
#   * The Celery beat task `api.tasks.check_stale_heartbeats` (hourly) alerts on instances that
#     stopped reporting a heartbeat.
#
# This function is kept as a no-op so existing imports in apps.py do not break.


def start_monitoring_thread():
    """No-op. Monitoring is now heartbeat-driven (see api.views.heartbeat / tasks.check_stale_heartbeats)."""
    logger.info(
        "Nidhi monitoring is heartbeat-driven (SCRUM-260); legacy polling thread not started."
    )
