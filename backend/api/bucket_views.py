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
    """Lists buckets the user has access to via their product assignments.
    Admin users (GOD MODE) see all buckets regardless of assignments."""
    sso_user_id = getattr(request, 'sso_user_id', None)
    if not sso_user_id and request.user and request.user.is_authenticated:
        sso_user_id = request.user.username
        
    if not sso_user_id:
        return Response({"error": "Missing SSO user context"}, status=status.HTTP_403_FORBIDDEN)
        
    assignments = EmployeeProductAssignment.objects.filter(sso_user_id=sso_user_id)
    
    # If no assignments (e.g., admin in GOD MODE), show all buckets
    if not assignments.exists():
        buckets = StorageBucket.objects.all().values(
            'id', 'bucket_name', 'endpoint', 'status', 'created_at', 'product__name',
            'server__name', 'server__host', 'server__environment_type'
        )
    else:
        product_ids = [a.product_id for a in assignments]
        buckets = StorageBucket.objects.filter(product_id__in=product_ids).values(
            'id', 'bucket_name', 'endpoint', 'status', 'created_at', 'product__name',
            'server__name', 'server__host', 'server__environment_type'
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
    
    assignments = EmployeeProductAssignment.objects.filter(sso_user_id=sso_user_id)
    if assignments.exists() and not assignments.filter(product_id=bucket.product_id).exists():
        return Response({"error": "Not authorized for this product."}, status=status.HTTP_403_FORBIDDEN)
        
    return Response({
        "bucket_name": bucket.bucket_name,
        "endpoint": bucket.endpoint,
        "access_key": bucket.access_key,
        "secret_key": bucket.secret_key
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsFoundingEngineer])
def list_bucket_objects(request, bucket_id):
    """Lists objects in a MinIO bucket with optional prefix for folder navigation.
    Supports recursive=true to return full tree structure."""
    bucket = get_object_or_404(StorageBucket, id=bucket_id)
    
    sso_user_id = getattr(request, 'sso_user_id', None)
    if not sso_user_id and request.user and request.user.is_authenticated:
        sso_user_id = request.user.username
    
    assignments = EmployeeProductAssignment.objects.filter(sso_user_id=sso_user_id)
    if assignments.exists() and not assignments.filter(product_id=bucket.product_id).exists():
        return Response({"error": "Not authorized for this product."}, status=status.HTTP_403_FORBIDDEN)
    
    if not Minio:
        return Response({"error": "MinIO SDK not installed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    prefix = request.GET.get('prefix', '')
    recursive = request.GET.get('recursive', 'false').lower() == 'true'
    
    try:
        # Map localhost to internal docker hostname for backend connection
        internal_endpoint = bucket.endpoint
        if internal_endpoint.startswith('localhost:'):
            internal_endpoint = MINIO_ENDPOINT
            
        # Use internal endpoint but bucket's credentials
        client = Minio(
            internal_endpoint,
            access_key=bucket.access_key,
            secret_key=bucket.secret_key,
            secure=False
        )
        
        objects = client.list_objects(bucket.bucket_name, prefix=prefix, recursive=recursive)
        object_list = []
        for obj in objects:
            object_list.append({
                "name": obj.object_name,
                "size": obj.size,
                "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
                "is_dir": obj.is_dir
            })
        
        if recursive:
            tree = build_tree(object_list)
            return Response(tree, status=status.HTTP_200_OK)
        
        return Response(object_list, status=status.HTTP_200_OK)
    except S3Error as e:
        return Response({"error": f"MinIO error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def build_tree(objects):
    """Build a nested tree structure from a flat list of MinIO objects."""
    root = {"name": "", "type": "directory", "children": []}
    
    for obj in objects:
        path = obj["name"]
        is_dir = obj.get("is_dir", False) or path.endswith("/")
        parts = [p for p in path.split("/") if p]
        
        current = root
        for i, part in enumerate(parts):
            is_last = (i == len(parts) - 1)
            existing = None
            for child in current["children"]:
                if child["name"] == part:
                    existing = child
                    break
            
            if existing:
                current = existing
            elif is_last and not is_dir:
                current["children"].append({
                    "name": part,
                    "type": "file",
                    "size": obj["size"],
                    "last_modified": obj["last_modified"],
                    "path": path
                })
            else:
                node = {"name": part, "type": "directory", "children": []}
                current["children"].append(node)
                current = node
    
    return root


@api_view(['POST'])
@permission_classes([IsFoundingEngineer])
def upload_object(request, bucket_id):
    """Uploads a file to a MinIO bucket."""
    bucket = get_object_or_404(StorageBucket, id=bucket_id)
    
    sso_user_id = getattr(request, 'sso_user_id', None)
    if not sso_user_id and request.user and request.user.is_authenticated:
        sso_user_id = request.user.username
    
    assignments = EmployeeProductAssignment.objects.filter(sso_user_id=sso_user_id)
    if assignments.exists() and not assignments.filter(product_id=bucket.product_id).exists():
        return Response({"error": "Not authorized for this product."}, status=status.HTTP_403_FORBIDDEN)
    
    if not Minio:
        return Response({"error": "MinIO SDK not installed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    if 'file' not in request.FILES:
        return Response({"error": "No file provided."}, status=status.HTTP_400_BAD_REQUEST)
    
    file_obj = request.FILES['file']
    object_name = request.data.get('object_name', file_obj.name)
    
    try:
        internal_endpoint = bucket.endpoint
        if internal_endpoint.startswith('localhost:'):
            internal_endpoint = MINIO_ENDPOINT
            
        client = Minio(
            internal_endpoint,
            access_key=bucket.access_key,
            secret_key=bucket.secret_key,
            secure=False
        )
        
        client.put_object(
            bucket.bucket_name,
            object_name,
            file_obj,
            length=file_obj.size,
            content_type=file_obj.content_type
        )
        
        return Response({"message": "File uploaded successfully", "object_name": object_name}, status=status.HTTP_200_OK)
    except S3Error as e:
        return Response({"error": f"MinIO error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsFoundingEngineer])
def delete_object(request, bucket_id):
    """Deletes an object from a MinIO bucket."""
    bucket = get_object_or_404(StorageBucket, id=bucket_id)
    
    sso_user_id = getattr(request, 'sso_user_id', None)
    if not sso_user_id and request.user and request.user.is_authenticated:
        sso_user_id = request.user.username
    
    assignments = EmployeeProductAssignment.objects.filter(sso_user_id=sso_user_id)
    if assignments.exists() and not assignments.filter(product_id=bucket.product_id).exists():
        return Response({"error": "Not authorized for this product."}, status=status.HTTP_403_FORBIDDEN)
    
    if not Minio:
        return Response({"error": "MinIO SDK not installed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    object_name = request.data.get('object_name')
    if not object_name:
        return Response({"error": "object_name is required."}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        internal_endpoint = bucket.endpoint
        if internal_endpoint.startswith('localhost:'):
            internal_endpoint = MINIO_ENDPOINT
            
        client = Minio(
            internal_endpoint,
            access_key=bucket.access_key,
            secret_key=bucket.secret_key,
            secure=False
        )
        
        client.remove_object(bucket.bucket_name, object_name)
        
        return Response({"message": "Object deleted successfully"}, status=status.HTTP_200_OK)
    except S3Error as e:
        return Response({"error": f"MinIO error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsFoundingEngineer])
def create_folder(request, bucket_id):
    """Creates a folder in a MinIO bucket by creating an empty object with trailing slash."""
    bucket = get_object_or_404(StorageBucket, id=bucket_id)
    
    sso_user_id = getattr(request, 'sso_user_id', None)
    if not sso_user_id and request.user and request.user.is_authenticated:
        sso_user_id = request.user.username
    
    assignments = EmployeeProductAssignment.objects.filter(sso_user_id=sso_user_id)
    if assignments.exists() and not assignments.filter(product_id=bucket.product_id).exists():
        return Response({"error": "Not authorized for this product."}, status=status.HTTP_403_FORBIDDEN)
    
    if not Minio:
        return Response({"error": "MinIO SDK not installed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    folder_name = request.data.get('folder_name')
    if not folder_name:
        return Response({"error": "folder_name is required."}, status=status.HTTP_400_BAD_REQUEST)
    
    # Ensure folder name ends with /
    if not folder_name.endswith('/'):
        folder_name = folder_name + '/'
    
    # Add current prefix if navigating in a subfolder
    current_prefix = request.data.get('prefix', '')
    if current_prefix and not current_prefix.endswith('/'):
        current_prefix = current_prefix + '/'
    
    full_path = current_prefix + folder_name
    
    try:
        from io import BytesIO
        
        internal_endpoint = bucket.endpoint
        if internal_endpoint.startswith('localhost:'):
            internal_endpoint = MINIO_ENDPOINT
            
        client = Minio(
            internal_endpoint,
            access_key=bucket.access_key,
            secret_key=bucket.secret_key,
            secure=False
        )
        
        # Create empty object with trailing slash to represent folder
        client.put_object(
            bucket.bucket_name,
            full_path,
            BytesIO(b''),
            length=0,
            content_type='application/x-directory'
        )
        
        return Response({"message": "Folder created successfully", "folder_path": full_path}, status=status.HTTP_200_OK)
    except S3Error as e:
        return Response({"error": f"MinIO error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

