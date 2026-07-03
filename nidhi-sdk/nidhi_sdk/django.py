import os


def inject_nidhi_storage(settings_module_locals: dict) -> None:
    """
    Injects django-storages S3Boto3 configuration into a Django settings module.

    Call this at the bottom of your Django settings.py:

        from nidhi_sdk import inject_nidhi_storage
        inject_nidhi_storage(locals())

    If the environment variable MEDIA_BUCKET_NAME is set (injected by nidhi-init.sh),
    this function:
      - Adds 'storages' to INSTALLED_APPS
      - Sets DEFAULT_FILE_STORAGE to S3Boto3Storage
      - Configures AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
        AWS_STORAGE_BUCKET_NAME, AWS_S3_ENDPOINT_URL, etc.

    Otherwise it falls back to FileSystemStorage.
    """
    locals_ = settings_module_locals

    if not os.environ.get('MEDIA_BUCKET_NAME'):
        locals_['DEFAULT_FILE_STORAGE'] = 'django.core.files.storage.FileSystemStorage'
        return

    locals_['AWS_ACCESS_KEY_ID'] = os.environ.get('MINIO_ACCESS_KEY')
    locals_['AWS_SECRET_ACCESS_KEY'] = os.environ.get('MINIO_SECRET_KEY')
    locals_['AWS_STORAGE_BUCKET_NAME'] = os.environ.get('MEDIA_BUCKET_NAME')

    minio_ep = os.environ.get('MINIO_ENDPOINT', 'minio:9000')
    if not minio_ep.startswith('http'):
        minio_ep = f"http://{minio_ep}"
    locals_['AWS_S3_ENDPOINT_URL'] = minio_ep

    locals_['AWS_S3_USE_SSL'] = False
    locals_['AWS_S3_SIGNATURE_VERSION'] = 's3v4'
    locals_['AWS_S3_FILE_OVERWRITE'] = False

    locals_['DEFAULT_FILE_STORAGE'] = 'storages.backends.s3boto3.S3Boto3Storage'

    if 'storages' not in locals_.get('INSTALLED_APPS', []):
        locals_['INSTALLED_APPS'] = list(locals_.get('INSTALLED_APPS', [])) + ['storages']
