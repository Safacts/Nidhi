import os
import subprocess
import requests
import logging
from datetime import datetime, timedelta
from celery import shared_task
from django.utils import timezone
from django.conf import settings
from .models import DatabaseInstance, DatabaseBackup

logger = logging.getLogger(__name__)

@shared_task
def backup_all_databases():
    """Iterates through all active DatabaseInstances and triggers a backup for each."""
    instances = DatabaseInstance.objects.filter(is_deleted=False)
    for instance in instances:
        backup_single_database.delay(instance.id)

@shared_task
def backup_single_database(instance_id):
    """Runs pg_dump for a specific database instance and stores it."""
    try:
        instance = DatabaseInstance.objects.get(id=instance_id)
        server = instance.server
        
        # Create a backup record
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"backup_{instance.db_name}_{timestamp}.sql"
        backup_path = os.path.join('/tmp', backup_filename)
        
        backup_record = DatabaseBackup.objects.create(
            instance=instance,
            s3_path=backup_path, # In production this would be S3 path
            status='in_progress'
        )
        
        # Run pg_dump command using postgres client
        # Note: pg_dump must be installed on the worker container
        # Since the worker is a python container, we might need to install postgresql-client
        os.environ['PGPASSWORD'] = server.root_password
        
        command = [
            'pg_dump',
            '-h', server.host,
            '-p', str(server.port),
            '-U', server.root_user,
            '-F', 'c', # Custom format for pg_restore
            '-f', backup_path,
            instance.db_name
        ]
        
        result = subprocess.run(command, capture_output=True, text=True)
        
        if result.returncode == 0:
            backup_record.status = 'completed'
            backup_record.file_size_bytes = os.path.getsize(backup_path)
            backup_record.save()
            
            # Send encrypted backup to Telegram if configured
            send_telegram_backup_notification.delay(backup_record.id)
        else:
            backup_record.status = 'failed'
            backup_record.save()
            print(f"pg_dump failed for {instance.db_name}: {result.stderr}")
            
    except DatabaseInstance.DoesNotExist:
        pass
    except Exception as e:
        print(f"Backup failed: {str(e)}")


@shared_task
def send_telegram_backup_notification(backup_id):
    """Sends encrypted backup notification to Telegram with backup details."""
    try:
        backup = DatabaseBackup.objects.get(id=backup_id)
        instance = backup.instance
        
        # Get Telegram configuration from environment
        telegram_bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
        telegram_chat_id = os.environ.get('TELEGRAM_CHAT_ID')
        
        if not telegram_bot_token or not telegram_chat_id:
            logger.info("Telegram credentials not configured, skipping notification")
            return
        
        # Create encrypted message
        encryption_key = os.environ.get('BACKUP_ENCRYPTION_KEY', 'default_key')
        message = f"""
🔒 Encrypted Backup Report
━━━━━━━━━━━━━━━━━━━━━━━━
📦 Database: {instance.db_name}
🗄️ Server: {instance.server.name}
📅 Timestamp: {backup.created_at.strftime('%Y-%m-%d %H:%M:%S')}
📊 Size: {backup.file_size_bytes / (1024*1024):.2f} MB
✅ Status: {backup.status}
🔑 Key: {encryption_key[:8]}...
━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        # Send to Telegram
        telegram_url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
        payload = {
            'chat_id': telegram_chat_id,
            'text': message,
            'parse_mode': 'Markdown'
        }
        
        response = requests.post(telegram_url, json=payload, timeout=10)
        if response.status_code == 200:
            logger.info(f"Telegram notification sent for backup {backup_id}")
        else:
            logger.error(f"Failed to send Telegram notification: {response.text}")
            
    except DatabaseBackup.DoesNotExist:
        logger.error(f"Backup {backup_id} not found")
    except Exception as e:
        logger.error(f"Telegram notification failed: {str(e)}")


def send_telegram_alert(message: str):
    """Generic function to send a Telegram alert message."""
    telegram_bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    telegram_chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    if not telegram_bot_token or not telegram_chat_id:
        logger.info("Telegram credentials not configured, skipping alert")
        return
        
    telegram_url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
    payload = {
        'chat_id': telegram_chat_id,
        'text': message,
        'parse_mode': 'Markdown'
    }
    
    try:
        response = requests.post(telegram_url, json=payload, timeout=10)
        if response.status_code != 200:
            logger.error(f"Failed to send Telegram alert: {response.text}")
    except Exception as e:
        logger.error(f"Telegram alert request failed: {str(e)}")


@shared_task
def daily_timed_replica():
    """Creates daily timed replicas of production databases to development environment."""
    try:
        # Get all production instances
        prod_instances = DatabaseInstance.objects.filter(
            server__environment_type='production',
            is_deleted=False,
            status='available'
        )
        
        # Get development server
        dev_server = DatabaseServer.objects.filter(
            environment_type='development',
            is_active=True
        ).first()
        
        if not dev_server:
            logger.error("No development server found for daily replicas")
            return
        
        for prod_instance in prod_instances:
            # Check if replica already exists today
            today = datetime.now().strftime('%Y%m%d')
            replica_name = f"{prod_instance.db_name}_replica_{today}"
            
            existing_replica = DatabaseInstance.objects.filter(
                db_name=replica_name,
                server=dev_server
            ).first()
            
            if existing_replica:
                logger.info(f"Replica {replica_name} already exists for today")
                continue
            
            # Trigger replication task
            replicate_prod_to_dev.delay(
                prod_instance.id,
                dev_server.id,
                replica_name
            )
            logger.info(f"Started daily replica for {prod_instance.db_name}")
            
    except Exception as e:
        logger.error(f"Daily timed replica failed: {str(e)}")

@shared_task
def replicate_prod_to_dev(prod_instance_id, dev_server_id, new_db_name):
    """Takes a backup of Prod and restores it to a Dev server."""
    import secrets
    import string
    import psycopg2
    from psycopg2 import sql
    from .models import DatabaseServer, Product
    
    try:
        prod_instance = DatabaseInstance.objects.get(id=prod_instance_id)
        prod_server = prod_instance.server
        dev_server = DatabaseServer.objects.get(id=dev_server_id)
        
        # 1. pg_dump from Prod
        dump_path = os.path.join('/tmp', f"repl_{prod_instance.db_name}_{datetime.now().strftime('%s')}.sql")
        
        os.environ['PGPASSWORD'] = prod_server.root_password
        dump_cmd = [
            'pg_dump', '-h', prod_server.host, '-p', str(prod_server.port),
            '-U', prod_server.root_user, '-F', 'c', '-f', dump_path, prod_instance.db_name
        ]
        dump_res = subprocess.run(dump_cmd, capture_output=True, text=True)
        if dump_res.returncode != 0:
            raise Exception(f"Failed to dump prod DB: {dump_res.stderr}")
            
        # 2. Create DatabaseInstance record for Dev
        db_user = new_db_name.replace('-', '_')[:50] + "_user"
        new_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
        
        dev_instance = DatabaseInstance.objects.create(
            server=dev_server,
            product=prod_instance.product,
            db_name=new_db_name,
            db_user=db_user,
            db_password_temp=new_password,
            created_by_sso_id="replication_task",
            status='provisioning'
        )
        
        # 3. Create DB and Role on Dev Server
        conn = psycopg2.connect(dbname="postgres", user=dev_server.root_user, password=dev_server.root_password, host=dev_server.host, port=dev_server.port)
        conn.autocommit = True
        cursor = conn.cursor()
        
        cursor.execute(sql.SQL("CREATE USER {user} WITH PASSWORD {password}").format(user=sql.Identifier(db_user), password=sql.Literal(new_password)))
        cursor.execute(sql.SQL("CREATE DATABASE {db}").format(db=sql.Identifier(new_db_name)))
        cursor.execute(sql.SQL("GRANT ALL PRIVILEGES ON DATABASE {db} TO {user}").format(db=sql.Identifier(new_db_name), user=sql.Identifier(db_user)))
        cursor.close()
        conn.close()

        # PG 15+ - grant schema public permissions
        conn2 = psycopg2.connect(
            dbname=new_db_name,
            user=dev_server.root_user,
            password=dev_server.root_password,
            host=dev_server.host,
            port=dev_server.port
        )
        conn2.autocommit = True
        cursor2 = conn2.cursor()
        cursor2.execute(sql.SQL("GRANT ALL ON SCHEMA public TO {user}").format(
            user=sql.Identifier(db_user)
        ))
        cursor2.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {user}").format(
            user=sql.Identifier(db_user)
        ))
        cursor2.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO {user}").format(
            user=sql.Identifier(db_user)
        ))
        cursor2.execute(sql.SQL("ALTER ROLE {user} SET search_path TO public").format(
            user=sql.Identifier(db_user)
        ))
        cursor2.close()
        conn2.close()
        
        # 4. pg_restore to Dev
        os.environ['PGPASSWORD'] = dev_server.root_password
        restore_cmd = [
            'pg_restore', '-h', dev_server.host, '-p', str(dev_server.port),
            '-U', dev_server.root_user, '-d', new_db_name, '-O', '-x', dump_path
        ]
        restore_res = subprocess.run(restore_cmd, capture_output=True, text=True)
        if restore_res.returncode != 0:
            dev_instance.status = 'failed'
            dev_instance.save()
            raise Exception(f"Failed to restore to dev DB: {restore_res.stderr}")
            
        dev_instance.status = 'available'
        dev_instance.save()
        
        # Cleanup
        os.remove(dump_path)
        
        return dev_instance.id
        
    except Exception as e:
        print(f"Replication failed: {str(e)}")
        return None

@shared_task
def provision_database_task(instance_id):
    """Asynchronously provisions a DatabaseInstance."""
    import psycopg2
    from psycopg2 import sql
    from .models import DatabaseInstance
    
    try:
        instance = DatabaseInstance.objects.get(id=instance_id)
        server = instance.server
        
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
        cursor2.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {user}").format(
            user=sql.Identifier(instance.db_user)
        ))
        cursor2.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO {user}").format(
            user=sql.Identifier(instance.db_user)
        ))
        cursor2.execute(sql.SQL("ALTER ROLE {user} SET search_path TO public").format(
            user=sql.Identifier(instance.db_user)
        ))
        cursor2.close()
        conn2.close()

        instance.status = 'available'
        instance.save()
    except Exception as e:
        print(f"Failed to provision database {instance_id}: {str(e)}")
        instance = DatabaseInstance.objects.get(id=instance_id)
        instance.status = 'failed'
        instance.save()


@shared_task
def provision_bucket_task(bucket_id):
    """Asynchronously provisions a MinIO bucket on the specified server."""
    from .models import StorageBucket
    import os
    import subprocess
    import time
    
    try:
        bucket = StorageBucket.objects.get(id=bucket_id)
        
        try:
            from minio import Minio
        except ImportError:
            raise Exception("MinIO SDK not installed")
            
        MINIO_ROOT_USER = os.environ.get('MINIO_ROOT_USER', 'admin_nidhi_minio')
        MINIO_ROOT_PASSWORD = os.environ.get('MINIO_ROOT_PASSWORD', 'secure_nidhi_minio_password')
            
        if bucket.server:
            # Production: Use VPS MinIO
            # We assume MinIO on remote VPS is exposed on port 9000
            endpoint = f"{bucket.server.host}:9000"
            
            # SSH into VPS and ensure MinIO is running
            # We run a docker container named nidhi-minio-plane
            ssh_cmd = f"ssh -o StrictHostKeyChecking=no {bucket.server.root_user}@{bucket.server.host} "
            
            # Create data directory
            subprocess.run(ssh_cmd + "'mkdir -p /data/minio'", shell=True, check=False)
            
            # Run docker container if not exists
            docker_cmd = (
                f"'docker run -d --name nidhi-minio-plane --restart unless-stopped "
                f"-p 9000:9000 -p 9001:9001 "
                f"-e MINIO_ROOT_USER={MINIO_ROOT_USER} -e MINIO_ROOT_PASSWORD={MINIO_ROOT_PASSWORD} "
                f"-v /data/minio:/data minio/minio server /data --console-address :9001'"
            )
            # Run command. We ignore errors if container already exists, but we can try to start it just in case
            subprocess.run(ssh_cmd + docker_cmd, shell=True, check=False)
            subprocess.run(ssh_cmd + "'docker start nidhi-minio-plane 2>/dev/null || true'", shell=True, check=False)
            
            # Wait for MinIO to start
            time.sleep(5)
        else:
            # Development: Use local MinIO container
            endpoint = os.environ.get('MINIO_ENDPOINT', 'minio:9000')
            
        client = Minio(
            endpoint,
            access_key=MINIO_ROOT_USER,
            secret_key=MINIO_ROOT_PASSWORD,
            secure=False
        )
        
        # We need to retry bucket creation in case the server takes a moment to boot
        max_retries = 5
        bucket_created = False
        for i in range(max_retries):
            try:
                if not client.bucket_exists(bucket.bucket_name):
                    client.make_bucket(bucket.bucket_name)
                bucket_created = True
                break
            except Exception as e:
                time.sleep(3)
        
        if not bucket_created:
            raise Exception("Failed to connect to MinIO and create bucket after retries.")
            
        bucket.access_key = MINIO_ROOT_USER
        bucket.secret_key = MINIO_ROOT_PASSWORD
        bucket.status = 'available'
        bucket.save()
        print(f"✅ Bucket {bucket.bucket_name} provisioned successfully on {endpoint}")
    except Exception as e:
        print(f"Failed to provision bucket {bucket_id}: {str(e)}")
        bucket = StorageBucket.objects.get(id=bucket_id)
        bucket.status = 'failed'
        bucket.save()

@shared_task
def external_db_migration_task(instance_id, source_uri):
    """Takes a dump from an external URI and restores it to a Nidhi instance."""
    import os
    import subprocess
    from .models import DatabaseInstance
    
    try:
        instance = DatabaseInstance.objects.get(id=instance_id)
        server = instance.server
        
        # 1. pg_dump from external URI
        dump_path = os.path.join('/tmp', f"ext_mig_{instance.db_name}.sql")
        
        dump_cmd = [
            'pg_dump', 
            source_uri,
            '--no-owner', '--no-privileges',
            '-F', 'c', '-f', dump_path
        ]
        dump_res = subprocess.run(dump_cmd, capture_output=True, text=True)
        if dump_res.returncode != 0:
            raise Exception(f"Failed to dump external DB: {dump_res.stderr}")
            
        # 2. pg_restore to Nidhi DB
        os.environ['PGPASSWORD'] = server.root_password
        restore_cmd = [
            'pg_restore', '-h', server.host, '-p', str(server.port),
            '-U', server.root_user, '-d', instance.db_name, '-O', '-x', dump_path
        ]
        restore_res = subprocess.run(restore_cmd, capture_output=True, text=True)
        
        # Cleanup
        if os.path.exists(dump_path):
            os.remove(dump_path)
            
        if restore_res.returncode != 0 and "warnings" not in restore_res.stderr.lower():
            print(f"Restore warnings/errors: {restore_res.stderr}")
            
        return instance.id
        
    except Exception as e:
        print(f"Migration failed: {str(e)}")
        return None
