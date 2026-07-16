"""
Nidhi SDK unit tests (nidhi_sdk).

TESTING_STRATEGY #13: the SDK must fail LOUD when Nidhi did not provision its
dependencies. We mock os.environ and requests.post (no network) and assert:
  * RuntimeError when MEDIA_BUCKET_NAME / DATABASE_URL is missing *in Docker*
    (no silent filesystem / sqlite fallback).
  * Correct injection when the env IS present.
  * send_heartbeat posts only a fingerprint and returns the right bool.
"""
import hashlib
import os
from urllib.parse import urlparse

from unittest import mock
import pytest

import nidhi_sdk.django as django_sdk
import nidhi_sdk.database as db_sdk


def _fake_dockerenv(in_docker):
    orig = os.path.exists

    def fake(p):
        if p == "/.dockerenv":
            return in_docker
        return orig(p)

    return fake


# ---------------------------------------------------------------------------
# Storage injection (inject_nidhi_storage)
# ---------------------------------------------------------------------------
def test_storage_missing_bucket_in_docker_raises():
    with mock.patch.object(os.path, "exists", side_effect=_fake_dockerenv(True)), \
         mock.patch.dict(os.environ, {}, clear=True):
        with pytest.raises(RuntimeError):
            django_sdk.inject_nidhi_storage({})


def test_storage_local_fallback_when_not_docker():
    with mock.patch.object(os.path, "exists", side_effect=_fake_dockerenv(False)), \
         mock.patch.dict(os.environ, {"MEDIA_BUCKET_NAME": "my-bucket"}, clear=True):
        locals_ = {"INSTALLED_APPS": []}
        django_sdk.inject_nidhi_storage(locals_)
        # In Docker only would it be an error; outside Docker it sets MinIO via env.
        assert locals_["AWS_STORAGE_BUCKET_NAME"] == "my-bucket"
        assert locals_["DEFAULT_FILE_STORAGE"] == "storages.backends.s3boto3.S3Boto3Storage"


# ---------------------------------------------------------------------------
# Database injection (inject_nidhi_database)
# ---------------------------------------------------------------------------
def test_database_missing_url_in_docker_raises():
    with mock.patch.object(os.path, "exists", side_effect=_fake_dockerenv(True)), \
         mock.patch.dict(os.environ, {}, clear=True):
        with pytest.raises(RuntimeError):
            django_sdk.inject_nidhi_database({})


def test_database_injects_when_url_present():
    url = "postgres://u:secret@db.example.com:6543/mydb"
    with mock.patch.object(os.path, "exists", side_effect=_fake_dockerenv(False)), \
         mock.patch.dict(os.environ, {"DATABASE_URL": url}, clear=True):
        locals_ = {}
        django_sdk.inject_nidhi_database(locals_)
        assert "DATABASES" in locals_
        assert locals_["DATABASES"]["default"]["ENGINE"] == "django.db.backends.postgresql"


# ---------------------------------------------------------------------------
# Fingerprint + heartbeat (database.py)
# ---------------------------------------------------------------------------
def test_get_database_fingerprint():
    url = "postgres://u:p@db.host.example.com:6543/mydb"
    expected = hashlib.sha256(b"db.host.example.com:6543/mydb").hexdigest()
    with mock.patch.dict(os.environ, {"DATABASE_URL": url}, clear=True):
        assert db_sdk.get_database_fingerprint() == expected


def test_send_heartbeat_success():
    url = "postgres://u:p@db.host.example.com:6543/mydb"
    env = {
        "NIDHI_API_URL": "http://nidhi-backend:8000/api",
        "NIDHI_APP_API_KEY": "secret-key",
        "PROJECT_SLUG": "new-nova",
        "NIDHI_ENVIRONMENT": "production",
        "DATABASE_URL": url,
    }
    fake_resp = mock.MagicMock()
    fake_resp.status_code = 200
    with mock.patch.dict(os.environ, env, clear=True), \
         mock.patch.object(db_sdk.requests, "post", return_value=fake_resp) as mock_post:
        ok = db_sdk.send_heartbeat()
    assert ok is True
    assert mock_post.called
    called_url = mock_post.call_args[0][0]
    assert called_url.endswith("/heartbeat/")
    payload = mock_post.call_args.kwargs["json"]
    assert payload["project_slug"] == "new-nova"
    assert payload["database_fingerprint"] == hashlib.sha256(
        b"db.host.example.com:6543/mydb").hexdigest()


def test_send_heartbeat_false_when_env_missing():
    with mock.patch.dict(os.environ, {}, clear=True):
        assert db_sdk.send_heartbeat() is False


def test_send_heartbeat_false_on_post_exception():
    url = "postgres://u:p@db.host.example.com:6543/mydb"
    env = {
        "NIDHI_API_URL": "http://nidhi-backend:8000/api",
        "NIDHI_APP_API_KEY": "secret-key",
        "PROJECT_SLUG": "new-nova",
        "DATABASE_URL": url,
    }
    with mock.patch.dict(os.environ, env, clear=True), \
         mock.patch.object(db_sdk.requests, "post", side_effect=Exception("boom")):
        assert db_sdk.send_heartbeat() is False
