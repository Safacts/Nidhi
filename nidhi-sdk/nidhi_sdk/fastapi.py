import os
import io

try:
    from minio import Minio
except ImportError:
    Minio = None


def get_nidhi_media_url(object_key: str) -> str:
    """
    Returns a URL that serves media through Nidhi's media gateway.
    The URL is authenticated (includes API key) and safe for browser use.

    MinIO is NEVER exposed directly. Every media request goes through
    Nidhi's /api/media/ endpoint which validates access and logs usage.

    Usage:
        url = get_nidhi_media_url("books/atomic-habits/pages/page1.png")
        # Returns: "http://100.83.65.7:8001/api/media/granth-production-media/books/...?api_key=..."
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


def get_nidhi_storage_client():
    """
    Returns a configured MinIO client and the target bucket name.
    For SERVER-SIDE operations only (upload, delete, list).
    Never use the returned client to generate browser-facing URLs —
    use get_nidhi_media_url() instead.
    """
    bucket_name = os.environ.get('MEDIA_BUCKET_NAME')
    if not bucket_name or not Minio:
        return None

    # Prefer MINIO_INTERNAL_HOST (Docker-internal) over MINIO_ENDPOINT
    internal_host = os.environ.get('MINIO_INTERNAL_HOST', '')
    endpoint = internal_host or os.environ.get('MINIO_ENDPOINT', 'minio:9000')

    access_key = os.environ.get('MINIO_ACCESS_KEY')
    secret_key = os.environ.get('MINIO_SECRET_KEY')

    client = Minio(
        endpoint,
        access_key=access_key,
        secret_key=secret_key,
        secure=False
    )
    return {
        'client': client,
        'bucket_name': bucket_name,
    }


def upload_file_to_nidhi(file_bytes: bytes, object_name: str, content_type: str = "application/octet-stream") -> str | None:
    """
    Uploads a file to the Nidhi-provisioned bucket.
    Returns the Nidhi media gateway URL to access the object, or None if not configured.
    """
    storage = get_nidhi_storage_client()
    if not storage:
        return None

    client = storage['client']
    bucket_name = storage['bucket_name']

    file_stream = io.BytesIO(file_bytes)
    client.put_object(
        bucket_name,
        object_name,
        file_stream,
        length=len(file_bytes),
        content_type=content_type,
    )

    return get_nidhi_media_url(object_name)


def delete_file_from_nidhi(object_name: str) -> bool:
    """
    Deletes an object from the Nidhi-provisioned bucket.
    """
    storage = get_nidhi_storage_client()
    if not storage:
        return False

    client = storage['client']
    bucket_name = storage['bucket_name']

    client.remove_object(bucket_name, object_name)
    return True


from urllib.parse import urlparse
from .telegram import send_telegram_alert

def get_nidhi_database_url() -> str:
    """
    Returns the Nidhi-provisioned DATABASE_URL.
    Crashes loudly if it is missing to prevent silent fallback errors.
    """
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        msg = (
            "❌ [Nidhi SDK] Required env var 'DATABASE_URL' is not set. "
            "Nidhi must provision it before the application starts."
        )
        if not os.path.exists('/tmp/.nidhi_notified_err'):
            send_telegram_alert(f"Application attempted to start without a Nidhi database connection!\n\n`{msg}`")
            with open('/tmp/.nidhi_notified_err', 'w') as f:
                f.write('1')
        raise RuntimeError(msg)
        
    db_name = os.environ.get('DB_NAME')
    if not db_name:
        db_name = urlparse(db_url).path.lstrip('/')
    msg = f"🐘 [Nidhi SDK] Injected PostgreSQL Database: {db_name}"
    
    if not os.path.exists('/tmp/.nidhi_notified'):
        send_telegram_alert(f"✅ Application successfully connected to Nidhi Database!\n\n`{msg}`")
        with open('/tmp/.nidhi_notified', 'w') as f:
            f.write('1')
            
    return db_url
