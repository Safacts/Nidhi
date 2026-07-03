import os
import dj_database_url

def inject_nidhi_storage(settings_module_locals: dict) -> None:
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
        locals_['INSTALLED_APPS'].append('storages')
    print(f"🪣 [Nidhi SDK] Activated MinIO Storage on bucket: {locals_['AWS_STORAGE_BUCKET_NAME']}")

from .telegram import send_telegram_alert
def inject_nidhi_database(settings_module_locals: dict) -> None:
    locals_ = settings_module_locals
    db_url = os.environ.get('DATABASE_URL')
    in_docker = os.path.exists('/.dockerenv')
    
    if db_url:
        if 'DATABASES' not in locals_:
            locals_['DATABASES'] = {}
            
        locals_['DATABASES']['default'] = dj_database_url.config(
            default=db_url, conn_max_age=600, ssl_require=False
        )
        msg = f"🐘 [Nidhi SDK] Injected PostgreSQL Database: {os.environ.get('DB_NAME')}"
        print(msg)
        send_telegram_alert(f"✅ Application successfully connected to Nidhi Database!\n\n`{msg}`")
    elif in_docker:
        msg = "❌ [Nidhi SDK] CRITICAL: Running in Docker but DATABASE_URL is missing. Nidhi must provision it."
        send_telegram_alert(f"Application attempted to start without a Nidhi database connection!\n\n`{msg}`")
        raise RuntimeError(msg)
