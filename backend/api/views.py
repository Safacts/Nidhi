# Owner / Founding Engineer: Aadisheshu (aadisheshu) — safacts founder & lead engineer.
# Contact: Telegram @aadisheshu (chat 1295597987). Off-site backup bot: @NidhiBackupBot.
import os
import io
import logging
import psycopg2
import requests
import secrets
import string
import subprocess
import tempfile
from psycopg2 import sql
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from django.http import StreamingHttpResponse
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.conf import settings
import hashlib
from .models import DatabaseServer, Product, DatabaseInstance, DatabaseBackup, EmployeeProductAssignment, StorageBucket, InstanceHeartbeat, SystemAlert, AuditLog
from .serializers import DatabaseServerSerializer, ProductSerializer, DatabaseInstanceSerializer, DatabaseBackupSerializer
from .permissions import IsFoundingEngineer, IsProductionDestructiveOp

try:
    from minio import Minio
    from minio.error import S3Error
except ImportError:
    Minio = None
    S3Error = None

logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes([AllowAny])
def sso_callback(request):
    code = request.data.get('code')
    if not code:
        return Response({'error': 'Authorization code is required.'}, status=status.HTTP_400_BAD_REQUEST)
    
    redirect_uri = request.data.get('redirect_uri', 'http://localhost:3000/auth/callback')
    
    token_url = getattr(settings, 'RUBIX_TOKEN_URL', 'https://novamymentor.in/o/token/')
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri,
        'client_id': os.environ.get('OAUTH_CLIENT_ID', 'nidhi_client_id_123'),
        'client_secret': os.environ.get('OAUTH_CLIENT_SECRET', 'nidhi_client_secret_xyz789_very_long_string_for_security'),
    }
    
    try:
        response = requests.post(token_url, data=data, timeout=10)
        if response.status_code == 200:
            token_data = response.json()
            return Response({'message': 'SSO Login successful!', 'token': token_data.get('access_token')}, status=status.HTTP_200_OK)
        else:
            return Response({'error': 'Failed to exchange token.', 'details': response.json()}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

from django.conf import settings

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def auto_register_server(request):
    """
    Autonomously register a new VPS node into the Data Plane.
    Protected by NIDHI_REGISTRATION_TOKEN.
    """
    token = request.headers.get('Authorization', '')
    expected_token = f"Bearer {getattr(settings, 'NIDHI_REGISTRATION_TOKEN', 'super_secret_default_token_xyz')}"
    
    if token != expected_token:
        return Response({"error": "Unauthorized registration token"}, status=status.HTTP_401_UNAUTHORIZED)
        
    data = request.data
    # Create the server directly
    try:
        server = DatabaseServer.objects.create(
            name=data.get('name', 'Auto-Registered Node'),
            host=data.get('host'),
            port=data.get('port', 5432),
            root_user=data.get('root_user', 'postgres'),
            root_password=data.get('root_password'),
            environment_type='production',
            is_active=True
        )
        return Response({"message": "Server registered successfully", "id": server.id}, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def auto_provision_instance(request):
    """
    Autonomously provisions or retrieves a DB for a startup app via init script.
    Protected by NIDHI_APP_API_KEY.
    """
    token = request.headers.get('Authorization', '')
    expected_token = f"Bearer {getattr(settings, 'NIDHI_APP_API_KEY', 'super_secret_app_api_key_123')}"
    
    if token != expected_token:
        return Response({"error": "Unauthorized API key"}, status=status.HTTP_401_UNAUTHORIZED)
        
    project_slug = request.data.get('project_slug', '').lower().replace(' ', '_')
    environment = request.data.get('environment', 'production').lower()
    
    if not project_slug:
        return Response({"error": "project_slug is required"}, status=status.HTTP_400_BAD_REQUEST)
        
    # Normalize: find existing product case-insensitively
    product = Product.objects.filter(name__iexact=project_slug).first()
    if not product:
        product = Product.objects.create(
            name=project_slug,
            description=f'Auto-created for {project_slug}'
        )
    
    # 2. Check if instance already exists (case-insensitive)
    existing_instance = DatabaseInstance.objects.filter(
        product=product,
        server__environment_type=environment,
        is_deleted=False
    ).first()
    
    if existing_instance:
        if existing_instance.status != 'available':
            return Response({"error": "Instance is not yet available"}, status=status.HTTP_400_BAD_REQUEST)
        
        db_url = f"postgres://{existing_instance.db_user}:{existing_instance.db_password_temp}@{existing_instance.server.host}:{existing_instance.server.port}/{existing_instance.db_name}"
        
        # Match bucket by name convention: {slug}-{environment}-media
        # (more reliable than server-based lookup since buckets can share the same server)
        bucket = StorageBucket.objects.filter(
            product=product,
            bucket_name__endswith="-" + environment + "-media",
            status='available'
        ).first()
        
        response_data = {"database_url": db_url}
        
        if bucket and bucket.status == 'available':
            response_data["bucket_name"] = bucket.bucket_name
            response_data["bucket_endpoint"] = bucket.endpoint
            response_data["bucket_id"] = str(bucket.id)
            if bucket.access_key and bucket.secret_key:
                response_data["bucket_access_key"] = bucket.access_key
                response_data["bucket_secret_key"] = bucket.secret_key
            # Media gateway URL — apps use this for browser-facing media access
            nidhi_server = os.environ.get("NIDHI_DEV_SERVER_URL", "")
            if nidhi_server:
                response_data["media_base_url"] = f"{nidhi_server.rstrip('/')}/api/media"
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    # 3. Find available server
    server = DatabaseServer.objects.filter(environment_type=environment, is_active=True).first()
    if not server:
        return Response({"error": f"No active server found for environment '{environment}'"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    # 4. Provision new database
    db_name = f"{project_slug.replace('-', '_')}_{environment}"[:50]
    db_user = f"{db_name}_user"[:50]
    
    if DatabaseInstance.objects.filter(db_name__iexact=db_name).exists():
        return Response({"error": "Database name conflict"}, status=status.HTTP_409_CONFLICT)
        
    new_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
    
    instance = DatabaseInstance(
        server=server,
        product=product,
        db_name=db_name,
        db_user=db_user,
        db_password_temp=new_password,
        created_by_sso_id='system-auto',
        status='provisioning',
        backup_enabled=(server.environment_type == 'production'),
    )
    instance.save()
    
    from .tasks import provision_database_task, provision_bucket_task
    provision_database_task.delay(instance.id)

    bucket_name = f"{project_slug}-{environment}-media"[:63]
    
    # Production buckets -> VPS MinIO; dev buckets -> devserver MinIO.
    if environment == "production":
        bucket_endpoint = os.environ.get("PRODUCTION_MINIO_ENDPOINT", "72.60.218.127:9000")
    elif environment == "development":
        bucket_endpoint = os.environ.get("PUBLIC_MINIO_ENDPOINT", "100.83.65.7:9000")
    else:
        # Default to devserver MinIO (laptop/local, future unknown environments)
        bucket_endpoint = os.environ.get("PUBLIC_MINIO_ENDPOINT", "100.83.65.7:9000")
    bucket_server = None


    MINIO_ROOT_USER = os.environ.get('MINIO_ROOT_USER', 'admin_nidhi_minio')
    MINIO_ROOT_PASSWORD = os.environ.get('MINIO_ROOT_PASSWORD', 'secure_nidhi_minio_password')
    
    bucket, _ = StorageBucket.objects.get_or_create(
        bucket_name=bucket_name,
        defaults={
            'product': product,
            'server': bucket_server,
            'access_key': MINIO_ROOT_USER,
            'secret_key': MINIO_ROOT_PASSWORD,
            'endpoint': bucket_endpoint,
            'created_by_sso_id': 'system-auto',
            'status': 'provisioning',
        }
    )
    if bucket.status == 'provisioning':
        provision_bucket_task.delay(bucket.id)

    db_url = f"postgres://{db_user}:{new_password}@{server.host}:{server.port}/{db_name}"
    
    # Return bucket credentials if available or provisioning
    bucket_response = {
        "bucket_name": bucket_name,
        "bucket_endpoint": bucket.endpoint,
        "bucket_id": str(bucket.id),
    }
    
    # Always include credentials if they are populated
    if bucket.access_key and bucket.secret_key:
        bucket_response["bucket_access_key"] = bucket.access_key
        bucket_response["bucket_secret_key"] = bucket.secret_key
    
    # Media gateway URL — apps use this for browser-facing media access
    nidhi_server = os.environ.get("NIDHI_DEV_SERVER_URL", "")
    if nidhi_server:
        bucket_response["media_base_url"] = f"{nidhi_server.rstrip('/')}/api/media"
    
    return Response({
        "database_url": db_url,
        **bucket_response,
    }, status=status.HTTP_202_ACCEPTED)

@api_view(['GET', 'POST'])
@permission_classes([IsFoundingEngineer])
def server_list_create(request):
    if request.method == 'GET':
        servers = DatabaseServer.objects.filter(is_active=True)
        serializer = DatabaseServerSerializer(servers, many=True)
        return Response(serializer.data)
    elif request.method == 'POST':
        serializer = DatabaseServerSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def product_list_create(request):
    if request.method == 'GET':
        products = Product.objects.all()
        serializer = ProductSerializer(products, many=True)
        return Response(serializer.data)
    elif request.method == 'POST':
        serializer = ProductSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def database_instance_list_create(request):
    if request.method == 'GET':
        instances = DatabaseInstance.objects.filter(is_deleted=False).order_by('-created_at')
        if getattr(request.user, 'role', '') != 'founding_engineer':
            assigned_product_ids = EmployeeProductAssignment.objects.filter(
                sso_user_id=request.user.username
            ).values_list('product_id', flat=True)
            instances = instances.filter(product_id__in=assigned_product_ids)
        serializer = DatabaseInstanceSerializer(instances, many=True)
        return Response(serializer.data)
        
    elif request.method == 'POST':
        server_id = request.data.get('server_id')
        product_id = request.data.get('product_id')
        db_name = request.data.get('db_name')
        created_by_sso_id = request.data.get('created_by_sso_id', 'system')
        
        if not server_id or not product_id or not db_name:
            return Response({"error": "server_id, product_id, and db_name are required."}, status=status.HTTP_400_BAD_REQUEST)
            
        server = get_object_or_404(DatabaseServer, id=server_id)
        product = get_object_or_404(Product, id=product_id)
        
        db_user = db_name.replace('-', '_')[:50] + "_user"
        
        if DatabaseInstance.objects.filter(db_name__iexact=db_name).exists():
            return Response({"error": "Database name already exists."}, status=status.HTTP_400_BAD_REQUEST)

        new_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for i in range(16))
        
        instance = DatabaseInstance(
            server=server,
            product=product,
            db_name=db_name,
            db_user=db_user,
            db_password_temp=new_password,
            created_by_sso_id=created_by_sso_id,
            status='provisioning',
            backup_enabled=(server.environment_type == 'production'),
        )
        instance.save()
        
        from .tasks import provision_database_task
        provision_database_task.delay(instance.id)

        serializer = DatabaseInstanceSerializer(instance)
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)

@api_view(['POST'])
@permission_classes([IsProductionDestructiveOp])
def delete_database(request, instance_id):
    """Soft Delete ONLY: revokes connect privilege and marks the record deleted, but the data is
    NEVER dropped. Hard DROP DATABASE is intentionally unavailable through the API — the
    2026-07-17 incident showed infra/script-level drops with no gate are the real risk.
    Every call is written to AuditLog for traceability."""
    instance = get_object_or_404(DatabaseInstance, id=instance_id, is_deleted=False)
    server = instance.server
    
    conn = None
    try:
        conn = psycopg2.connect(
            dbname="postgres",
            user=server.root_user,
            password=server.root_password,
            host=server.host,
            port=server.port
        )
        conn.autocommit = True
        cursor = conn.cursor()

        # Revoke connect privilege from public and the specific user
        revoke_query = sql.SQL("REVOKE CONNECT ON DATABASE {db_name} FROM PUBLIC, {user};").format(
            db_name=sql.Identifier(instance.db_name),
            user=sql.Identifier(instance.db_user)
        )
        cursor.execute(revoke_query)
        
        # Optionally, terminate active connections to immediately enforce revocation
        terminate_query = sql.SQL("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s;")
        cursor.execute(terminate_query, [instance.db_name])
        
        cursor.close()
        
        # Soft delete record
        instance.is_deleted = True
        instance.deleted_at = timezone.now()
        instance.status = 'stopped'
        instance.save()

        from .models import AuditLog
        AuditLog.objects.create(
            actor_type='founding_engineer',
            actor=getattr(request.user, 'username', 'unknown'),
            action='soft_delete_db',
            target=instance.db_name,
            server=instance.server.name,
            detail='Soft-delete (revoke connect). Data retained.',
            ip_address=request.META.get('REMOTE_ADDR'),
            success=True,
        )
        return Response({"message": "Database access revoked and soft deleted successfully. Data was retained (no DROP)."}, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({"error": f"Failed to soft-delete database: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        if conn:
            conn.close()

@api_view(['GET'])
@permission_classes([IsFoundingEngineer])
def reveal_credentials(request, instance_id):
    instance = get_object_or_404(DatabaseInstance, id=instance_id, is_deleted=False)
    credentials = {
        "host": instance.server.host,
        "port": instance.server.port,
        "db_name": instance.db_name,
        "db_user": instance.db_user,
        "db_password": instance.db_password_temp,
        "connection_string": f"postgres://{instance.db_user}:{instance.db_password_temp}@{instance.server.host}:{instance.server.port}/{instance.db_name}"
    }
    return Response(credentials, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([IsFoundingEngineer])
def replicate_to_dev(request, instance_id):
    """Triggers the Celery task to replicate a Prod DB to a Dev server."""
    prod_instance = get_object_or_404(DatabaseInstance, id=instance_id, is_deleted=False)
    
    dev_server_id = request.data.get('dev_server_id')
    new_db_name = request.data.get('new_db_name')
    
    if not dev_server_id or not new_db_name:
        return Response({"error": "dev_server_id and new_db_name are required."}, status=status.HTTP_400_BAD_REQUEST)
        
    from .tasks import replicate_prod_to_dev
    
    # Trigger celery task
    replicate_prod_to_dev.delay(prod_instance.id, dev_server_id, new_db_name)
    
    return Response({
        "message": "Replication task triggered successfully.",
        "source_db": prod_instance.db_name,
        "target_db": new_db_name
    }, status=status.HTTP_202_ACCEPTED)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me(request):
    return Response({
        'username': request.user.username,
        'role': getattr(request.user, 'role', 'employee')
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def alert_list(request):
    from .models import SystemAlert
    from .serializers import SystemAlertSerializer
    alerts = SystemAlert.objects.all().order_by('-created_at')[:50]
    serializer = SystemAlertSerializer(alerts, many=True)
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def alert_mark_read(request, alert_id):
    from .models import SystemAlert
    try:
        alert = SystemAlert.objects.get(id=alert_id)
        alert.is_read = True
        alert.save()
        return Response({"status": "marked read"}, status=status.HTTP_200_OK)
    except SystemAlert.DoesNotExist:
        return Response({"error": "not found"}, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def alert_mark_all_read(request):
    from .models import SystemAlert
    SystemAlert.objects.filter(is_read=False).update(is_read=True)
    return Response({"status": "all marked read"}, status=status.HTTP_200_OK)


def compute_db_fingerprint(host, port, db_name):
    """Deterministic fingerprint of a DB identity (no credentials). SCRUM-260."""
    raw = f"{(host or '').strip().lower()}:{port}/{(db_name or '').strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def heartbeat(request):
    """SCRUM-260: bypass detection.

    Apps POST {project_slug, environment, database_fingerprint} periodically. The fingerprint is
    a sha256 of host:port/db (NO password). Nidhi compares it to the instance it provisioned; a
    mismatch means the app is NOT using its Nidhi database (SQLite/hardcoded fallback) and raises
    a Telegram alert + SystemAlert.
    """
    from .tasks import send_telegram_alert

    token = request.headers.get('Authorization', '')
    expected_token = f"Bearer {getattr(settings, 'NIDHI_APP_API_KEY', 'super_secret_app_api_key_123')}"
    if token != expected_token:
        return Response({"error": "Unauthorized API key"}, status=status.HTTP_401_UNAUTHORIZED)

    project_slug = request.data.get('project_slug', '').lower().replace(' ', '_')
    environment = request.data.get('environment', 'production').lower()
    reported_fp = request.data.get('database_fingerprint', '')

    if not project_slug or not reported_fp:
        return Response(
            {"error": "project_slug and database_fingerprint are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    product = Product.objects.filter(name__iexact=project_slug).first()
    if not product:
        return Response({"error": "Unknown project"}, status=status.HTTP_404_NOT_FOUND)

    instance = DatabaseInstance.objects.filter(
        product=product, server__environment_type=environment, is_deleted=False
    ).first()
    if not instance:
        return Response({"error": "No provisioned instance for project/environment"},
                        status=status.HTTP_404_NOT_FOUND)

    expected_fp = compute_db_fingerprint(
        instance.server.host, instance.server.port, instance.db_name
    )
    is_valid = (reported_fp == expected_fp)

    hb, _ = InstanceHeartbeat.objects.get_or_create(instance=instance)
    was_valid = hb.is_valid
    hb.reported_fingerprint = reported_fp
    hb.expected_fingerprint = expected_fp
    hb.is_valid = is_valid
    hb.last_heartbeat_at = timezone.now()
    hb.stale_alerted = False
    if not is_valid:
        # Only alert on transition into an invalid state to avoid spam.
        if was_valid or hb.last_alerted_at is None:
            msg = (
                f"🚨 *Nidhi Bypass Detected*\n"
                f"App `{project_slug}` ({environment}) reported a database fingerprint that does "
                f"NOT match its provisioned instance `{instance.db_name}`.\n"
                f"It may be running on SQLite or a hardcoded database."
            )
            send_telegram_alert(msg)
            SystemAlert.objects.create(
                title=f"Database Bypass: {instance.db_name}",
                message=(f"App {project_slug} ({environment}) reported fingerprint {reported_fp} "
                         f"which does not match provisioned instance {instance.db_name}."),
                level="error",
            )
            hb.last_alerted_at = timezone.now()
    else:
        if not was_valid:
            send_telegram_alert(
                f"✅ *Nidhi Recovery*\nApp `{project_slug}` ({environment}) is now using its "
                f"provisioned database `{instance.db_name}` again."
            )
            SystemAlert.objects.create(
                title=f"Database Bypass Resolved: {instance.db_name}",
                message=f"App {project_slug} ({environment}) reconnected to {instance.db_name}.",
                level="info",
            )
    hb.save()

    return Response({"status": "ok", "valid": is_valid}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsFoundingEngineer])
def backups_overview(request):
    """Backups monitoring: latest backup per instance, off-site status, age, and recent audit."""
    from django.utils import timezone as tz
    data = []
    for inst in DatabaseInstance.objects.filter(is_deleted=False).order_by('db_name'):
        latest = inst.backups.order_by('-created_at').first()
        age_hours = None
        if latest and latest.created_at:
            age_hours = round((tz.now() - latest.created_at).total_seconds() / 3600, 1)
        data.append({
            "instance_id": str(inst.id),
            "db_name": inst.db_name,
            "server": inst.server.name,
            "status": inst.status,
            "latest_backup_id": str(latest.id) if latest else None,
            "latest_backup_status": latest.status if latest else None,
            "latest_backup_at": latest.created_at.isoformat() if latest else None,
            "age_hours": age_hours,
            "off_site_configured": bool(os.environ.get('TELEGRAM_BOT_TOKEN') and os.environ.get('TELEGRAM_CHAT_ID')),
        })
    recent = [
        {"at": a.created_at.isoformat(), "actor": a.actor, "action": a.action,
         "target": a.target, "success": a.success, "detail": (a.detail or "")[:200]}
        for a in AuditLog.objects.all().order_by('-created_at')[:25]
    ]
    return Response({
        "backups": data,
        "recent_audit": recent,
        "now": tz.now().isoformat(),
    })


@api_view(['POST'])
@permission_classes([IsFoundingEngineer])
def trigger_backup(request, instance_id):
    """Manually trigger an on-demand backup for an instance (queues Celery task)."""
    from .tasks import backup_single_database
    inst = get_object_or_404(DatabaseInstance, id=instance_id, is_deleted=False)
    backup_single_database.delay(str(inst.id))
    AuditLog.objects.create(
        actor_type='founding_engineer', actor=getattr(request.user, 'username', 'unknown'),
        action='backup_db', target=inst.db_name, server=inst.server.name,
        detail='Manual backup triggered', success=True,
    )
    return Response({"message": f"Backup queued for {inst.db_name}."}, status=status.HTTP_202_ACCEPTED)


# ── Media Gateway ──────────────────────────────────────────────────────────
# MinIO is NEVER exposed to the internet. Every media request goes through
# this endpoint which validates access, logs usage, and streams the object.
# Apps use the SDK's get_nidhi_media_url() to generate URLs pointing here.

MINIO_ROOT_USER = os.environ.get('MINIO_ROOT_USER', 'admin_nidhi_minio')
MINIO_ROOT_PASSWORD = os.environ.get('MINIO_ROOT_PASSWORD', 'secure_nidhi_minio_password')


def _get_minio_client_for_bucket(bucket):
    """Returns a Minio client configured for the given bucket's stored endpoint."""
    if not Minio:
        return None
    endpoint = bucket.endpoint
    if endpoint in ('localhost:9000', 'minio:9000', '127.0.0.1:9000'):
        endpoint = os.environ.get('MINIO_ENDPOINT', '100.83.65.7:9000')
    return Minio(endpoint, access_key=bucket.access_key, secret_key=bucket.secret_key, secure=False)


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def serve_media(request, bucket_name, object_key):
    """
    Secure media proxy. Authenticates via NIDHI_APP_API_KEY (query param or header),
    validates bucket ownership, streams from MinIO. Never exposes MinIO directly.

    Usage: GET /api/media/<bucket_name>/<object_key>?api_key=<key>

    MinIO is NEVER exposed directly. This is the only way to access media.
    """
    if not Minio:
        return Response({"error": "MinIO SDK not installed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Authenticate: check API key from query param or Authorization header
    api_key = request.GET.get('api_key', '') or request.headers.get('Authorization', '').replace('Bearer ', '')
    expected_key = getattr(settings, 'NIDHI_APP_API_KEY', 'super_secret_app_api_key_123')
    if not api_key or api_key != expected_key:
        logger.warning("Media gateway: unauthorized access attempt for %s/%s", bucket_name, object_key)
        return Response({"error": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

    # Look up bucket
    try:
        bucket = StorageBucket.objects.select_related('product').get(bucket_name=bucket_name, status='available')
    except StorageBucket.DoesNotExist:
        logger.warning("Media gateway: bucket not found: %s", bucket_name)
        return Response({"error": "Bucket not found"}, status=status.HTTP_404_NOT_FOUND)

    # Ownership check: bucket must belong to an active product
    if not bucket.product:
        logger.warning("Media gateway: orphaned bucket %s (no product)", bucket_name)
        return Response({"error": "Bucket has no associated product"}, status=status.HTTP_403_FORBIDDEN)

    # Fetch from MinIO
    try:
        client = _get_minio_client_for_bucket(bucket)
        if not client:
            return Response({"error": "MinIO not available"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        obj = client.get_object(bucket_name, object_key)
        content_type = obj.headers.get('Content-Type', 'application/octet-stream')
        data = obj.read()
        obj.close()
        obj.release_conn()

        # Log access: who (api_key hash), what (bucket/key), when, from where
        ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:12]
        logger.info(
            "Media access: key=%s bucket=%s object=%s product=%s ip=%s size=%d",
            key_hash, bucket_name, object_key, bucket.product.name, ip, len(data),
        )

        response = StreamingHttpResponse(
            io.BytesIO(data),
            content_type=content_type,
        )
        response['Content-Length'] = len(data)
        # Cache for 1 day — browsers cache, reducing proxy load
        response['Cache-Control'] = 'public, max-age=86400'
        if hasattr(obj, 'etag') and obj.etag:
            response['ETag'] = obj.etag
        return response

    except Exception as e:
        if 'NoSuchKey' in str(e) or 'NoSuchKey' in str(type(e).__name__):
            return Response({"error": "Object not found"}, status=status.HTTP_404_NOT_FOUND)
        logger.error("Media gateway: fetch failed for %s/%s: %s", bucket_name, object_key, e)
        return Response({"error": f"Media fetch failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def minio_backups_overview(request):
    """Returns MinIO backup status — last pull time, size, bucket-level summary."""
    # Auth: accept either app API key or valid SSO token
    api_key = request.GET.get('api_key', '') or request.headers.get('Authorization', '').replace('Bearer ', '')
    expected_key = getattr(settings, 'NIDHI_APP_API_KEY', 'super_secret_app_api_key_123')
    if not api_key or api_key != expected_key:
        # Fallback: check SSO token via IsFoundingEngineer manual check
        from .permissions import IsFoundingEngineer
        perm = IsFoundingEngineer()
        if not perm.has_permission(request, None):
            return Response({"error": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
    
    from datetime import datetime, timedelta
    from .models import BackupStatus, StorageBucket

    _disk_cache = {"ts": 0.0, "value": None}

    now = timezone.now()

    def _last_run(kind):
        return BackupStatus.objects.filter(kind=kind).order_by('-started_at').first()

    def _staleness_hours(run):
        if not run or not run.finished_at:
            return None
        return round((now - run.finished_at).total_seconds() / 3600, 1)

    # ---- Nidhi control-plane ledger (source of truth, replaces host cron log) ----
    media_run = _last_run('minio_media')
    dbcopy_run = _last_run('db_copy_tb')

    # Staleness: media expected daily ~02:30, db-copy daily ~00:15. Alert if >26h since success.
    media_age = _staleness_hours(media_run)
    dbcopy_age = _staleness_hours(dbcopy_run)
    STALE_HOURS = 26

    media_healthy = bool(media_run and media_run.status in ('completed', 'partial') and media_age is not None and media_age < STALE_HOURS)
    dbcopy_healthy = bool(dbcopy_run and dbcopy_run.status == 'completed' and dbcopy_age is not None and dbcopy_age < STALE_HOURS)
    replica_run = _last_run('bucket_replica')
    replica_age = _staleness_hours(replica_run)
    replica_healthy = bool(replica_run and replica_run.status in ('completed', 'partial') and replica_age is not None and replica_age < STALE_HOURS)
    overall_healthy = media_healthy and dbcopy_healthy and replica_healthy

    # Bucket-level on-disk summary (TB disk mirror). Cached 5 min because os.walk over
    # ~3.7 GB / 71k files is slow and would block the single dev-server worker.
    backup_dir = '/host_backups/minio/'
    now_ts = timezone.now().timestamp()
    if _disk_cache["value"] is not None and (now_ts - _disk_cache["ts"]) < 300:
        buckets, total_size, total_objects = _disk_cache["value"]
    else:
        buckets = []
        total_size = 0
        total_objects = 0
        try:
            if os.path.isdir(backup_dir):
                for bname in sorted(os.listdir(backup_dir)):
                    bpath = os.path.join(backup_dir, bname)
                    if os.path.isdir(bpath):
                        size = count = 0
                        for root, dirs, files in os.walk(bpath):
                            for f in files:
                                fp = os.path.join(root, f)
                                try:
                                    size += os.path.getsize(fp)
                                    count += 1
                                except OSError:
                                    pass
                        total_size += size
                        total_objects += count
                        buckets.append({
                            'bucket_name': bname,
                            'objects': count,
                            'size_bytes': size,
                            'size_mb': round(size / 1024 / 1024, 2),
                        })
        except Exception:
            pass
        _disk_cache["value"] = (buckets, total_size, total_objects)
        _disk_cache["ts"] = now_ts

    # VPS MinIO live source status (lightweight: list_buckets only — NO recursive object
    # counting, which is slow over tens of thousands of objects and blocks the single
    # dev-server worker). The on-disk mirror already reports size/object counts.
    live_objects = live_size = 0
    vps_healthy = dev_healthy = False
    try:
        from minio import Minio as MinioClient
        prod = MinioClient('72.60.218.127:9000', access_key='admin_nidhi_minio',
                           secret_key='secure_nidhi_minio_password', secure=False)
        prod.list_buckets()
        vps_healthy = True
    except Exception:
        vps_healthy = False
    try:
        dev = MinioClient('172.21.0.1:9000', access_key='admin_nidhi_minio',
                          secret_key='secure_nidhi_minio_password', secure=False)
        dev.list_buckets()
        dev_healthy = True
    except Exception:
        dev_healthy = False

    # Recent control-plane runs for the UI feed
    recent_runs = []
    try:
        for r in BackupStatus.objects.filter(kind__in=['minio_media', 'db_copy_tb', 'bucket_replica']).order_by('-started_at')[:10]:
            recent_runs.append({
                'kind': r.kind,
                'target': r.target,
                'status': r.status,
                'started_at': r.started_at.isoformat(),
                'finished_at': r.finished_at.isoformat() if r.finished_at else None,
                'items_ok': r.items_ok,
                'items_failed': r.items_failed,
                'bytes_transferred': r.bytes_transferred,
                'destination': r.destination,
            })
    except Exception:
        recent_runs = []

    return Response({
        'last_backup_at': media_run.finished_at.isoformat() if media_run and media_run.finished_at else None,
        'last_backup_status': media_run.status if media_run else 'never',
        'backup_directory': backup_dir,
        'backup_size_bytes': total_size,
        'backup_size_gb': round(total_size / 1024 / 1024 / 1024, 2),
        'backup_objects': total_objects,
        'buckets': buckets,
        'vps_live': {
            'objects': live_objects,
            'size_bytes': live_size,
            'size_gb': round(live_size / 1024 / 1024 / 1024, 2),
        },
        'health': {
            'overall': 'healthy' if overall_healthy else 'DEGRADED',
            'media_backup': 'healthy' if media_healthy else 'STALE/FAILED',
            'db_copy': 'healthy' if dbcopy_healthy else 'STALE/FAILED',
            'bucket_replication': 'healthy' if replica_healthy else 'STALE/FAILED',
            'vps_minio': 'healthy' if vps_healthy else 'DOWN',
            'dev_minio': 'healthy' if dev_healthy else 'DOWN',
            'media_age_hours': media_age,
            'db_copy_age_hours': dbcopy_age,
            'checked_at': now.isoformat(),
        },
        'backup_schedule': 'Nidhi-managed (Celery beat): minio_media 02:30 daily, db_copy_tb 00:15 daily, bucket_replica 03:00 daily',
        'backup_location': '/host_backups/minio/ (devserver TB hard disk)',
        'control_plane_runs': recent_runs,
    }, status=status.HTTP_200_OK)
@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def retrieve_cached_credentials(request, project_slug, environment):
    """
    Returns credentials for an already-provisioned product instance.
    Use this when devserver was down and app needs to re-fetch credentials
    WITHOUT triggering auto-provision (which creates new resources).
    """
    from .models import Product, DatabaseInstance, StorageBucket
    
    project_slug = project_slug.lower().replace(' ', '_')
    environment = environment.lower()
    
    # Auth check
    token = request.headers.get('Authorization', '')
    expected_token = f"Bearer {getattr(settings, 'NIDHI_APP_API_KEY', 'super_secret_app_api_key_123')}"
    if token != expected_token:
        return Response({"error": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
    
    product = Product.objects.filter(name__iexact=project_slug).first()
    if not product:
        return Response({"error": f"No product found for '{project_slug}'"}, status=status.HTTP_404_NOT_FOUND)
    
    # Look up existing instance (do NOT create)
    instance = DatabaseInstance.objects.filter(
        product=product,
        server__environment_type=environment,
        is_deleted=False
    ).first()
    
    if not instance:
        return Response({"error": f"No {environment} instance found for '{project_slug}'. Use auto-provision to create one."}, status=status.HTTP_404_NOT_FOUND)
    
    db_url = f"postgres://{instance.db_user}:{instance.db_password_temp}@{instance.server.host}:{instance.server.port}/{instance.db_name}"
    
    bucket = StorageBucket.objects.filter(
        product=product,
        bucket_name__endswith="-" + environment + "-media",
        status='available'
    ).first()
    
    result = {"database_url": db_url}
    
    if bucket:
        result["bucket_name"] = bucket.bucket_name
        result["bucket_endpoint"] = bucket.endpoint
        result["bucket_id"] = str(bucket.id)
        if bucket.access_key and bucket.secret_key:
            result["bucket_access_key"] = bucket.access_key
            result["bucket_secret_key"] = bucket.secret_key
    
    return Response(result, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsFoundingEngineer])
def toggle_instance_backup(request, instance_id):
    """Enable/disable Nidhi backup for a DatabaseInstance (per-instance opt-in).

    Production instances are locked ON (cannot be disabled via UI). Development
    instances may be toggled. Body: {"backup_enabled": true|false}
    """
    inst = get_object_or_404(DatabaseInstance, id=instance_id, is_deleted=False)
    if inst.is_production and not request.data.get('backup_enabled', True):
        return Response(
            {"error": "Production databases are always backed up and cannot be disabled."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    enabled = bool(request.data.get('backup_enabled', not inst.backup_enabled))
    inst.backup_enabled = enabled
    inst.save(update_fields=['backup_enabled', 'updated_at'])
    AuditLog.objects.create(
        actor_type='founding_engineer', actor=getattr(request.user, 'username', 'unknown'),
        action='toggle_backup', target=inst.db_name, server=inst.server.name,
        detail=f"backup_enabled set to {enabled}", success=True,
    )
    return Response(
        {"id": str(inst.id), "db_name": inst.db_name, "backup_enabled": inst.backup_enabled},
        status=status.HTTP_200_OK,
    )
