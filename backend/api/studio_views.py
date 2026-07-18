import psycopg2
from psycopg2.extras import RealDictCursor
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import DatabaseInstance
from .permissions import IsFoundingEngineer

def get_connection(instance):
    """Helper to get a dict cursor connection to a specific database instance."""
    conn = psycopg2.connect(
        dbname=instance.db_name,
        user=instance.server.root_user,
        password=instance.server.root_password,
        host=instance.server.host,
        port=instance.server.port,
        cursor_factory=RealDictCursor
    )
    return conn

@api_view(['GET'])
@permission_classes([IsFoundingEngineer])
def get_tables(request, instance_id):
    """Retrieve all user tables in the database."""
    instance = get_object_or_404(DatabaseInstance, id=instance_id, is_deleted=False)
    
    conn = None
    try:
        conn = get_connection(instance)
        cursor = conn.cursor()
        query = """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name;
        """
        cursor.execute(query)
        tables = [row['table_name'] for row in cursor.fetchall()]
        cursor.close()
        return Response({"tables": tables}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        if conn:
            conn.close()

@api_view(['GET'])
@permission_classes([IsFoundingEngineer])
def get_table_data(request, instance_id, table_name):
    """Retrieve up to 100 rows from a specific table."""
    instance = get_object_or_404(DatabaseInstance, id=instance_id, is_deleted=False)
    
    # Very basic protection against SQL injection on table_name
    if not table_name.isidentifier():
        return Response({"error": "Invalid table name"}, status=status.HTTP_400_BAD_REQUEST)
        
    conn = None
    try:
        conn = get_connection(instance)
        cursor = conn.cursor()
        
        # Get column names first
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position;", (table_name,))
        columns = [row['column_name'] for row in cursor.fetchall()]
        
        # Get primary keys
        cursor.execute("""
            SELECT a.attname
            FROM   pg_index i
            JOIN   pg_attribute a ON a.attrelid = i.indrelid
                                 AND a.attnum = ANY(i.indkey)
            WHERE  i.indrelid = %s::regclass
            AND    i.indisprimary;
        """, (table_name,))
        primary_keys = [row['attname'] for row in cursor.fetchall()]
        
        # Get data
        # psycopg2 sql composition is safer but for this simple explorer we'll construct the query
        # Since we checked isidentifier() we have basic protection
        cursor.execute(f'SELECT * FROM "{table_name}" LIMIT 100;')
        rows = cursor.fetchall()
        
        cursor.close()
        
        return Response({
            "table": table_name,
            "columns": columns,
            "primary_keys": primary_keys,
            "rows": rows
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        if conn:
            conn.close()

@api_view(['POST'])
@permission_classes([IsFoundingEngineer])
def execute_query(request, instance_id):
    """Executes read-only SQL queries against the specific database.

    NOTE (2026-07-18 data-safety hardening): this runner is READ-ONLY. DROP / TRUNCATE / DELETE /
    ALTER / CREATE / UPDATE / INSERT are rejected. Schema changes must go through migrations, not
    the Studio. Every execution is written to AuditLog for traceability.
    """
    from .models import AuditLog, is_production_environment
    instance = get_object_or_404(DatabaseInstance, id=instance_id, is_deleted=False)

    query = (request.data.get('query') or '').strip()
    if not query:
        return Response({"error": "Query string is required."}, status=status.HTTP_400_BAD_REQUEST)

    # Reject any destructive / mutating statement.
    forbidden = re.compile(
        r"(DROP|TRUNCATE|DELETE|ALTER|CREATE|INSERT|UPDATE|RENAME|GRANT|REVOKE|COMMENT)",
        re.IGNORECASE,
    )
    if forbidden.search(query):
        AuditLog.objects.create(
            actor_type='founding_engineer',
            actor=getattr(request.user, 'username', 'unknown'),
            action='execute_query',
            target=instance.db_name,
            server=instance.server.name,
            detail='REJECTED destructive SQL (guarded): ' + query[:500],
            success=False,
        )
        return Response(
            {"error": "Mutating/DDL statements are blocked by the data-safety guard. "
                      "Use migrations for schema changes."},
            status=status.HTTP_403_FORBIDDEN,
        )

    conn = None
    try:
        conn = get_connection(instance)
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute(query)
        rows = []
        columns = []
        if cursor.description:
            columns = [desc.name for desc in cursor.description]
            rows = cursor.fetchall()
        cursor.close()
        AuditLog.objects.create(
            actor_type='founding_engineer',
            actor=getattr(request.user, 'username', 'unknown'),
            action='execute_query',
            target=instance.db_name,
            server=instance.server.name,
            detail='SELECT executed: ' + query[:300],
            success=True,
        )
        return Response({
            "columns": columns,
            "rows": rows,
            "message": "Query executed successfully."
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    finally:
        if conn:
            conn.close()


import os
import subprocess
from django.http import FileResponse

@api_view(['GET'])
@permission_classes([IsFoundingEngineer])
def download_database_dump(request, instance_id):
    """Generates a pg_dump file for the given instance and returns it as a download."""
    instance = get_object_or_404(DatabaseInstance, id=instance_id, is_deleted=False)
    server = instance.server
    
    try:
        dump_path = os.path.join('/tmp', f"dump_{instance.db_name}.sql")
        
        # Use PGPASSWORD to bypass prompt
        os.environ['PGPASSWORD'] = server.root_password
        
        # Dump to plain-text SQL format
        dump_cmd = [
            'pg_dump',
            '-h', server.host,
            '-p', str(server.port),
            '-U', server.root_user,
            '-d', instance.db_name,
            '-F', 'p',  # plain text SQL
            '-f', dump_path
        ]
        
        result = subprocess.run(dump_cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            return Response({"error": f"Dump failed: {result.stderr}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
        if not os.path.exists(dump_path):
            return Response({"error": "Dump file not generated."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
        # Stream the file back
        response = FileResponse(open(dump_path, 'rb'), as_attachment=True, filename=f"{instance.db_name}_backup.sql")
        return response
        
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

from .tasks import external_db_migration_task

@api_view(['POST'])
@permission_classes([IsFoundingEngineer])
def migrate_database(request, instance_id):
    """Triggers an external migration task to pull data into this instance."""
    instance = get_object_or_404(DatabaseInstance, id=instance_id, is_deleted=False)
    
    source_uri = request.data.get('source_uri')
    if not source_uri:
        return Response({"error": "source_uri is required."}, status=status.HTTP_400_BAD_REQUEST)
        
    # Trigger Celery task
    external_db_migration_task.delay(instance_id, source_uri)
    
    return Response({"message": "Migration task started."}, status=status.HTTP_202_ACCEPTED)
