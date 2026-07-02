import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nidhi_backend.settings')
django.setup()

import secrets
import string
from api.models import Product, DatabaseServer, DatabaseInstance
from api.tasks import provision_database_task

def provision_db(product_name, server_id, db_name):
    product, _ = Product.objects.get_or_create(name=product_name)
    server = DatabaseServer.objects.get(id=server_id)
    
    db_user = db_name.replace('-', '_')[:50] + "_user"
    new_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
    
    instance = DatabaseInstance.objects.create(
        server=server,
        product=product,
        db_name=db_name,
        db_user=db_user,
        db_password_temp=new_password,
        created_by_sso_id="automation",
        status='provisioning'
    )
    
    # Provision synchronously for reliability here instead of relying on celery queue
    # which might not pick it up if there are issues
    from psycopg2 import sql
    import psycopg2
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

        create_user_query = sql.SQL("CREATE USER {user} WITH PASSWORD {password}").format(
            user=sql.Identifier(instance.db_user), 
            password=sql.Literal(instance.db_password_temp)
        )
        create_db_query = sql.SQL("CREATE DATABASE {db_name}").format(
            db_name=sql.Identifier(instance.db_name)
        )
        grant_privs_query = sql.SQL("GRANT ALL PRIVILEGES ON DATABASE {db_name} TO {user}").format(
            db_name=sql.Identifier(instance.db_name), 
            user=sql.Identifier(instance.db_user)
        )

        cursor.execute(create_user_query)
        cursor.execute(create_db_query)
        cursor.execute(grant_privs_query)
        cursor.close()
        conn.close()

        # PG 15+ - grant schema public permissions
        conn2 = psycopg2.connect(
            dbname=instance.db_name,
            user=server.root_user,
            password=server.root_password,
            host=server.host,
            port=server.port
        )
        conn2.autocommit = True
        cursor2 = conn2.cursor()
        cursor2.execute(sql.SQL("GRANT ALL ON SCHEMA public TO {user}").format(
            user=sql.Identifier(instance.db_user)
        ))
        cursor2.close()
        conn2.close()

        instance.status = 'available'
        instance.save()
        print(f"Provisioned {db_name} on {server.name}")
    except Exception as e:
        print(f"Failed to provision database {db_name}: {str(e)}")
        instance.status = 'failed'
        instance.save()

# 1. Vitharn (dev)
provision_db("Vitharn", 1, "vitharn_dev")

# 2. Aacharya (dev)
provision_db("Aacharya", 1, "aacharya_dev")

# 3. New-nova (dev)
provision_db("new-nova", 1, "new_nova_dev")

# 4. New-nova (prod)
provision_db("new-nova", 2, "new_nova_prod")
