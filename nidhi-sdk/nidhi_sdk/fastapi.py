import os
import io

try:
    from minio import Minio
except ImportError:
    Minio = None


def get_nidhi_storage_client():
    """
    Returns a configured MinIO client and the target bucket name,
    using environment variables injected by nidhi-init.sh.
    """
    bucket_name = os.environ.get('MEDIA_BUCKET_NAME')

    endpoint = os.environ.get('MINIO_ENDPOINT', 'minio:9000')
    if endpoint.startswith('localhost:'):
        endpoint = 'minio:9000'

    access_key = os.environ.get('MINIO_ACCESS_KEY')
    secret_key = os.environ.get('MINIO_SECRET_KEY')

    if not bucket_name or not Minio:
        return None

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
    Returns the URL/path to access the object, or None if Nidhi storage is not configured.
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

    return f"/{bucket_name}/{object_name}"


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

def get_nidhi_database_url() -> str:
    """
    Returns the Nidhi-provisioned DATABASE_URL.
    Crashes loudly if it is missing to prevent silent fallback errors.
    """
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        raise RuntimeError(
            "❌ [Nidhi SDK] Required env var 'DATABASE_URL' is not set. "
            "Nidhi must provision it before the application starts."
        )
    return db_url
