import os
import dj_database_url

from .telegram import send_telegram_alert


def get_nidhi_media_url(object_key: str) -> str:
    """
    Returns a URL that serves media through Nidhi's media gateway.
    MinIO is NEVER exposed directly. Every media request goes through
    Nidhi's /api/media/ endpoint which validates access and logs usage.
    """
    nidhi_url = os.environ.get('NIDHI_DEV_SERVER_URL', '')
    bucket = os.environ.get('MEDIA_BUCKET_NAME', '')
    api_key = os.environ.get('NIDHI_APP_API_KEY', '')

    if not nidhi_url or not bucket:
        raise RuntimeError(
            "NIDHI_DEV_SERVER_URL or MEDIA_BUCKET_NAME not set. "
            "App must be provisioned by Nidhi."
        )

    return f"{nidhi_url.rstrip('/')}/api/media/{bucket}/{object_key}?api_key={api_key}"


def inject_nidhi_storage(settings_module_locals: dict) -> None:
    locals_ = settings_module_locals
    in_docker = os.path.exists("/.dockerenv")
    bucket_name = os.environ.get("MEDIA_BUCKET_NAME")

    if not bucket_name:
        if in_docker:
            msg = (
                "❌ [Nidhi SDK] CRITICAL: Running in Docker but MEDIA_BUCKET_NAME is missing. "
                "Nidhi must provision a storage bucket before the application starts. "
                "No silent fallback to local filesystem allowed."
            )
            if not os.path.exists("/tmp/.nidhi_storage_err"):
                send_telegram_alert(
                    f"Application attempted to start without Nidhi storage!\n\n`{msg}`"
                )
                with open("/tmp/.nidhi_storage_err", "w") as f:
                    f.write("1")
            raise RuntimeError(msg)
        else:
            print("⚠️ [Nidhi SDK] No MEDIA_BUCKET_NAME set, using local FileSystemStorage (non-Docker)")
            locals_["DEFAULT_FILE_STORAGE"] = "django.core.files.storage.FileSystemStorage"
            return

    locals_["AWS_ACCESS_KEY_ID"] = os.environ.get("MINIO_ACCESS_KEY")
    locals_["AWS_SECRET_ACCESS_KEY"] = os.environ.get("MINIO_SECRET_KEY")
    locals_["AWS_STORAGE_BUCKET_NAME"] = bucket_name

    # Prefer MINIO_INTERNAL_HOST (Docker-internal) over MINIO_ENDPOINT
    internal_host = os.environ.get("MINIO_INTERNAL_HOST", "")
    minio_ep = internal_host or os.environ.get("MINIO_ENDPOINT", "minio:9000")
    if not minio_ep.startswith("http"):
        minio_ep = f"http://{minio_ep}"
    locals_["AWS_S3_ENDPOINT_URL"] = minio_ep

    locals_["AWS_S3_USE_SSL"] = False
    locals_["AWS_S3_SIGNATURE_VERSION"] = "s3v4"
    locals_["AWS_S3_FILE_OVERWRITE"] = False

    locals_["DEFAULT_FILE_STORAGE"] = "storages.backends.s3boto3.S3Boto3Storage"

    if "storages" not in locals_.get("INSTALLED_APPS", []):
        locals_["INSTALLED_APPS"].append("storages")
    print(f"🪣 [Nidhi SDK] Activated MinIO Storage on bucket: {bucket_name}")


def inject_nidhi_database(settings_module_locals: dict) -> None:
    locals_ = settings_module_locals
    db_url = os.environ.get("DATABASE_URL")
    in_docker = os.path.exists("/.dockerenv")

    if db_url:
        if "DATABASES" not in locals_:
            locals_["DATABASES"] = {}

        locals_["DATABASES"]["default"] = dj_database_url.config(
            default=db_url, conn_max_age=600, ssl_require=False
        )
        from urllib.parse import urlparse

        db_name = os.environ.get("DB_NAME")
        if not db_name:
            db_name = urlparse(db_url).path.lstrip("/")
        msg = f"🐘 [Nidhi SDK] Injected PostgreSQL Database: {db_name}"
        print(msg)
        if not os.path.exists("/tmp/.nidhi_notified"):
            send_telegram_alert(
                f"✅ Application successfully connected to Nidhi Database!\n\n`{msg}`"
            )
            with open("/tmp/.nidhi_notified", "w") as f:
                f.write("1")
    elif in_docker:
        msg = (
            "❌ [Nidhi SDK] CRITICAL: Running in Docker but DATABASE_URL is missing. "
            "Nidhi must provision it before the application starts."
        )
        if not os.path.exists("/tmp/.nidhi_notified_err"):
            send_telegram_alert(
                f"Application attempted to start without a Nidhi database connection!\n\n`{msg}`"
            )
            with open("/tmp/.nidhi_notified_err", "w") as f:
                f.write("1")
        raise RuntimeError(msg)
