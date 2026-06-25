import os
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import StorageBucket, Product, EmployeeProductAssignment, DatabaseServer
from .permissions import IsFoundingEngineer
import secrets
import string

try:
    from minio import Minio
    from minio.error import S3Error
except ImportError:
    Minio = None

# Using internal docker network hostname if available, else localhost
MINIO_ENDPOINT = os.environ.get('MINIO_ENDPOINT', 'minio:9000')
MINIO_ROOT_USER = os.environ.get('MINIO_ROOT_USER', 'admin_nidhi_minio')
MINIO_ROOT_PASSWORD = os.environ.get('MINIO_ROOT_PASSWORD', 'secure_nidhi_minio_password')
# For returning to the client (we assume it's exposed on localhost:9000 for local dev)
PUBLIC_MINIO_ENDPOINT = os.environ.get('PUBLIC_MINIO_ENDPOINT', 'localhost:9000')

def get_minio_client():
    if not Minio:
        return None
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ROOT_USER,
        secret_key=MINIO_ROOT_PASSWORD,
        secure=False
    )

def generate_random_string(length=20):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for i in range(length))

@api_view(['POST'])
@permission_classes([IsFoundingEngineer])
def provision_bucket(request):
    """Provisions a new MinIO bucket."""
    if not Minio:
        return Response({"error": "MinIO SDK not installed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    bucket_name = request.data.get('bucket_name')
    product_id = request.data.get('product_id')
    server_id = request.data.get('server_id')
    
    if not bucket_name or not product_id:
        return Response({"error": "bucket_name and product_id are required."}, status=status.HTTP_400_BAD_REQUEST)

    # Clean bucket name (lowercase, no spaces)
    bucket_name = bucket_name.lower().replace(' ', '-')
    
    product = get_object_or_404(Product, id=product_id)
    server = None
    endpoint = PUBLIC_MINIO_ENDPOINT
    
    if server_id:
        server = get_object_or_404(DatabaseServer, id=server_id)
        endpoint = f"{server.host}:9000"
    
    sso_user_id = getattr(request, 'sso_user_id', None)
    if not sso_user_id and request.user and request.user.is_authenticated:
        sso_user_id = request.user.username
    if not sso_user_id:
        sso_user_id = 'unknown'
    
    if StorageBucket.objects.filter(bucket_name=bucket_name).exists():
        return Response({"error": "Bucket name already exists."}, status=status.HTTP_400_BAD_REQUEST)
        
    bucket = StorageBucket.objects.create(
        product=product,
        server=server,
        bucket_name=bucket_name,
        access_key='',
        secret_key='',
        endpoint=endpoint,
        created_by_sso_id=sso_user_id,
        status='provisioning'
    )
    
    from .tasks import provision_bucket_task
    provision_bucket_task.delay(bucket.id)
    
    return Response({
        "id": bucket.id,
        "bucket_name": bucket.bucket_name,
        "status": bucket.status
    }, status=status.HTTP_202_ACCEPTED)


@api_view(['GET'])
@permission_classes([IsFoundingEngineer])
def list_buckets(request):
    """Lists buckets the user has access to via their product assignments."""
    sso_user_id = getattr(request, 'sso_user_id', None)
    if not sso_user_id and request.user and request.user.is_authenticated:
        sso_user_id = request.user.username
        
    if not sso_user_id:
        return Response({"error": "Missing SSO user context"}, status=status.HTTP_403_FORBIDDEN)
        
    assignments = EmployeeProductAssignment.objects.filter(sso_user_id=sso_user_id)
    product_ids = [a.product_id for a in assignments]
    
    buckets = StorageBucket.objects.filter(product_id__in=product_ids).values(
        'id', 'bucket_name', 'endpoint', 'status', 'created_at', 'product__name'
    )
    
    return Response(list(buckets), status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsFoundingEngineer])
def reveal_bucket_credentials(request, bucket_id):
    """Reveals the access and secret keys for a bucket."""
    bucket = get_object_or_404(StorageBucket, id=bucket_id)
    
    sso_user_id = getattr(request, 'sso_user_id', None)
    if not sso_user_id and request.user and request.user.is_authenticated:
        sso_user_id = request.user.username
    if not EmployeeProductAssignment.objects.filter(sso_user_id=sso_user_id, product_id=bucket.product_id).exists():
        return Response({"error": "Not authorized for this product."}, status=status.HTTP_403_FORBIDDEN)
        
    return Response({
        "bucket_name": bucket.bucket_name,
        "endpoint": bucket.endpoint,
        "access_key": bucket.access_key,
        "secret_key": bucket.secret_key
    }, status=status.HTTP_200_OK)
