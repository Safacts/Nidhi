# Founding Engineer: Aadisheshu <safacts001@gmail.com>
import os
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
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import DatabaseServer, Product, DatabaseInstance, DatabaseBackup, EmployeeProductAssignment, StorageBucket
from .serializers import DatabaseServerSerializer, ProductSerializer, DatabaseInstanceSerializer, DatabaseBackupSerializer
from .permissions import IsFoundingEngineer

@api_view(['POST'])
@permission_classes([AllowAny])
def sso_callback(request):
    code = request.data.get('code')
    if not code:
        return Response({'error': 'Authorization code is required.'}, status=status.HTTP_400_BAD_REQUEST)
    
    redirect_uri = request.data.get('redirect_uri', 'http://localhost:3000/auth/callback')
    
    token_url = getattr(settings, 'RUBIX_TOKEN_URL', 'https://rubix.novamymentor.cloud/o/token/')
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
        status='provisioning'
    )
    instance.save()
    
    from .tasks import provision_database_task, provision_bucket_task
    provision_database_task.delay(instance.id)

    bucket_name = f"{project_slug}-{environment}-media"[:63]
    
    # For dev: use local MinIO (server=None), for prod: use VPS MinIO (server=prod_server)
    bucket_server = None
    bucket_endpoint = os.environ.get('PUBLIC_MINIO_ENDPOINT', 'localhost:9000')
    
    if environment == 'production':
        prod_server = DatabaseServer.objects.filter(environment_type='production', is_active=True).first()
        if prod_server:
            bucket_server = prod_server
            bucket_endpoint = f"{prod_server.host}:9000"
    
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
            status='provisioning'
        )
        instance.save()
        
        from .tasks import provision_database_task
        provision_database_task.delay(instance.id)

        serializer = DatabaseInstanceSerializer(instance)
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)

@api_view(['POST'])
@permission_classes([IsFoundingEngineer])
def delete_database(request, instance_id):
    """Soft Delete: Revokes access on the DB but keeps the data intact."""
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
        
        return Response({"message": "Database access revoked and soft deleted successfully."}, status=status.HTTP_200_OK)

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
