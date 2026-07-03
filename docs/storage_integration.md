# Nidhi Storage Client Integration

This document outlines how Nidhi handles automated MinIO bucket storage for the Rubix Ecosystem platforms (Aacharya, New-Nova, Vitharn, etc.).

## How it works

Nidhi provides automated storage provisioning. When a bucket is provisioned in the Nidhi Control Plane, its credentials are dynamically injected into the respective applications at runtime via the `nidhi-init.sh` entrypoint script.

The injected environment variables include:
- `MEDIA_BUCKET_NAME`
- `MINIO_ENDPOINT`
- `MINIO_ACCESS_KEY`
- `MINIO_SECRET_KEY`

## Adding Nidhi Storage to New Applications

While the `nidhi-init.sh` script automatically injects the *credentials*, new applications require a small piece of code to consume those credentials properly.

### For Django Applications

Add the following block to your `settings.py` file to automatically route all `FileField` and `ImageField` uploads to the Nidhi bucket when available. Ensure `django-storages` and `boto3` are in your `requirements.txt`.

```python
# ==============================================================================
# 🪣 NIDHI AUTOMATED STORAGE INJECTION
# ==============================================================================
import os

if os.environ.get('MEDIA_BUCKET_NAME'):
    AWS_ACCESS_KEY_ID = os.environ.get('MINIO_ACCESS_KEY')
    AWS_SECRET_ACCESS_KEY = os.environ.get('MINIO_SECRET_KEY')
    AWS_STORAGE_BUCKET_NAME = os.environ.get('MEDIA_BUCKET_NAME')
    
    minio_ep = os.environ.get('MINIO_ENDPOINT', 'minio:9000')
    if not minio_ep.startswith('http'):
        minio_ep = f"http://{minio_ep}"
    AWS_S3_ENDPOINT_URL = minio_ep
    
    AWS_S3_USE_SSL = False
    AWS_S3_SIGNATURE_VERSION = 's3v4'
    AWS_S3_FILE_OVERWRITE = False
    
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    
    if 'storages' not in INSTALLED_APPS:
        INSTALLED_APPS.append('storages')
else:
    DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
```

### For FastAPI Applications

Create a `nidhi_storage.py` utility file (usually in `utils/` or `core/`) with the standard Nidhi MinIO SDK boilerplate. This allows you to call `upload_file_to_nidhi()` natively in your routes.

Ensure `minio` is in your `requirements.txt`.

```python
import os
import io

try:
    from minio import Minio
except ImportError:
    Minio = None

def get_nidhi_storage_client():
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
    return {'client': client, 'bucket_name': bucket_name}

def upload_file_to_nidhi(file_bytes: bytes, object_name: str, content_type: str = "application/octet-stream") -> str:
    storage = get_nidhi_storage_client()
    if not storage: return None
    storage['client'].put_object(storage['bucket_name'], object_name, io.BytesIO(file_bytes), length=len(file_bytes), content_type=content_type)
    return f"/{storage['bucket_name']}/{object_name}"
```

*(Note: Future iterations of Nidhi may package this as a standalone `nidhi-sdk` private PyPI package, eliminating the need to copy-paste the boilerplate code.)*
