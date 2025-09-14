# backend/api/views.py

# --- Corrected and complete imports ---
import requests
import os
import psycopg2
import secrets
import string
from psycopg2 import sql
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from .models import DatabaseRequest
from .serializers import DatabaseRequestSerializer
from .permissions import IsAuthenticatedUser, IsAdminUser

# --- Constants ---
ATTENDANCE_API_URL = os.getenv("ATTENDANCE_API_URL")

# --- Authentication View ---
@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    username = request.data.get('username')
    password = request.data.get('password')

    if not username or not password:
        return Response({"error": "Username and password are required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        token_response = requests.post(f"{ATTENDANCE_API_URL}/api/users/token/", json={"username": username, "password": password}, timeout=10)
        token_response.raise_for_status()
        tokens = token_response.json()
    except requests.exceptions.HTTPError:
        return Response({"error": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)
    except requests.exceptions.RequestException as e:
        return Response({"error": "Could not connect to authentication service.", "details": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    try:
        access_token = tokens.get('access')
        headers = {'Authorization': f'Bearer {access_token}'}
        profile_response = requests.get(f"{ATTENDANCE_API_URL}/api/users/profile/", headers=headers, timeout=10)
        profile_response.raise_for_status()
        user_profile = profile_response.json()
    except requests.exceptions.RequestException as e:
        return Response({"error": "Could not retrieve user profile.", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({"tokens": tokens, "user": user_profile}, status=status.HTTP_200_OK)


# --- User/Faculty Views ---
@api_view(['POST'])
@permission_classes([IsAuthenticatedUser])
def create_database_request(request):
    user_id = request.headers.get('X-User-Id')
    user_name = request.headers.get('X-User-Name')

    serializer = DatabaseRequestSerializer(data=request.data)
    if serializer.is_valid():
        db_user = serializer.validated_data['db_name'].replace('-', '_')[:50] + "_user"
        serializer.save(student_id=user_id, student_username=user_name, db_user=db_user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([IsAuthenticatedUser])
def list_my_requests(request):
    user_id = request.headers.get('X-User-Id')
    requests = DatabaseRequest.objects.filter(student_id=user_id).order_by('-created_at')
    serializer = DatabaseRequestSerializer(requests, many=True)
    return Response(serializer.data)


# --- Admin Views ---
@api_view(['GET'])
@permission_classes([IsAdminUser])
def list_pending_requests(request):
    requests = DatabaseRequest.objects.filter(status='pending').order_by('created_at')
    serializer = DatabaseRequestSerializer(requests, many=True)
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def approve_database_request(request, request_id):
    try:
        db_request = DatabaseRequest.objects.get(id=request_id, status='pending')
    except DatabaseRequest.DoesNotExist:
        return Response({"error": "Request not found or already processed."}, status=status.HTTP_404_NOT_FOUND)

    new_db_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for i in range(16))
    conn = None
    try:
        conn = psycopg2.connect(
            dbname="postgres",
            user=os.getenv('PI_DB_USER'),
            password=os.getenv('PI_DB_PASSWORD'),
            host=os.getenv('PI_DB_HOST'),
            port=os.getenv('PI_DB_PORT')
        )
        conn.autocommit = True
        cursor = conn.cursor()

        # ---- NEW, CORRECTED CODE ----
        # Build the queries using the safe, explicit sql.Literal for the password
        create_user_query = sql.SQL("CREATE USER {user} WITH PASSWORD {password}").format(
            user=sql.Identifier(db_request.db_user),
            password=sql.Literal(new_db_password) # This is the crucial fix
        )
        create_db_query = sql.SQL("CREATE DATABASE {db_name}").format(db_name=sql.Identifier(db_request.db_name))
        grant_privs_query = sql.SQL("GRANT ALL PRIVILEGES ON DATABASE {db_name} TO {user}").format(
            db_name=sql.Identifier(db_request.db_name),
            user=sql.Identifier(db_request.db_user)
        )

        # Execute the corrected queries
        cursor.execute(create_user_query)
        cursor.execute(create_db_query)
        cursor.execute(grant_privs_query)
        cursor.close()

        db_request.status = 'approved'
        db_request.approved_by = request.headers.get('X-User-Name')
        db_request.save()

        return Response({
            "message": "Database created successfully.",
            "db_name": db_request.db_name,
            "db_user": db_request.db_user,
            "db_password": new_db_password
        }, status=status.HTTP_200_OK)

    except Exception as e:
        db_request.status = 'error'
        db_request.save()
        return Response({"error": f"Failed to create database: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        if conn:
            conn.close()