"""Nidhi SDK — database module (SCRUM-295 / SCRUM-260).

Single import surface for database concerns:

    from nidhi_sdk.database import (
        get_nidhi_database_url,   # fetch the provisioned DATABASE_URL (crashes if missing)
        inject_nidhi_database,    # wire DATABASE_URL into Django settings
        get_database_fingerprint, # sha256(host:port/db) of the DB actually in use
        send_heartbeat,           # report that fingerprint to Nidhi (bypass detection)
    )

The provisioning helpers are re-exported from their original modules for backwards compatibility
so existing `from nidhi_sdk.fastapi import get_nidhi_database_url` / `from nidhi_sdk.django import
inject_nidhi_database` imports keep working unchanged.
"""
import os
import hashlib
from urllib.parse import urlparse

import requests

from .fastapi import get_nidhi_database_url
from .django import inject_nidhi_database

__all__ = [
    "get_nidhi_database_url",
    "inject_nidhi_database",
    "get_database_fingerprint",
    "send_heartbeat",
]


def get_database_fingerprint(db_url: str | None = None) -> str | None:
    """Return sha256 of host:port/db for the given (or env) DATABASE_URL. No credentials included."""
    db_url = db_url or os.environ.get("DATABASE_URL")
    if not db_url:
        return None
    parsed = urlparse(db_url)
    host = (parsed.hostname or "").strip().lower()
    port = parsed.port or 5432
    db_name = (parsed.path or "").lstrip("/").strip().lower()
    raw = f"{host}:{port}/{db_name}"
    return hashlib.sha256(raw.encode()).hexdigest()


def send_heartbeat(timeout: int = 5) -> bool:
    """Report the DATABASE_URL fingerprint to Nidhi so it can detect bypass (SCRUM-260).

    Uses env vars injected by nidhi-init.sh:
        NIDHI_API_URL       e.g. http://nidhi-backend:8000/api  (or the public base)
        NIDHI_APP_API_KEY   shared secret (Bearer)
        PROJECT_SLUG        the app's project slug
        NIDHI_ENVIRONMENT   'production' | 'development' (defaults to production)

    Never sends credentials — only a fingerprint. Returns True on a 2xx response.
    """
    api_url = os.environ.get("NIDHI_API_URL")
    api_key = os.environ.get("NIDHI_APP_API_KEY")
    project_slug = os.environ.get("PROJECT_SLUG")
    environment = os.environ.get("NIDHI_ENVIRONMENT", "production")

    if not api_url or not api_key or not project_slug:
        return False

    fingerprint = get_database_fingerprint()
    if not fingerprint:
        return False

    try:
        resp = requests.post(
            f"{api_url.rstrip('/')}/heartbeat/",
            json={
                "project_slug": project_slug,
                "environment": environment,
                "database_fingerprint": fingerprint,
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
        return 200 <= resp.status_code < 300
    except Exception:
        return False
