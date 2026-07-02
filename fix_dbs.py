import os
import django
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nidhi_backend.settings')
django.setup()

from api.models import DatabaseInstance, StorageBucket

instances = DatabaseInstance.objects.all()
for instance in instances:
    print(f"DB Instance: {instance.db_name}, User: {instance.db_user}, Slug: {getattr(instance, 'project_slug', 'N/A')}")
    if 'vitarn' in instance.db_name.lower() or getattr(instance, 'project_slug', '').lower() == 'vitarn':
        print(f"-> Planning to delete {instance.db_name}")
        try:
            conn = psycopg2.connect(
                dbname="postgres",
                user=instance.server.root_user,
                password=instance.server.root_password,
                host=instance.server.host,
                port=instance.server.port
            )
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            with conn.cursor() as cur:
                cur.execute(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{instance.db_name}';")
                cur.execute(f"DROP DATABASE IF EXISTS {instance.db_name};")
                cur.execute(f"DROP USER IF EXISTS {instance.db_user};")
            conn.close()
            print("Dropped DB via postgres.")
        except Exception as e:
            print(f"Failed to drop {instance.db_name}: {e}")
        instance.delete()
        print("Deleted instance record from Nidhi.")

