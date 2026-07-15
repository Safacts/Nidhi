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

# Telegram sendDocument hard limit is 50MB for bots. Keep a safety margin.
TELEGRAM_MAX_PART_BYTES = 49 * 1024 * 1024

# Persistent on-server copy of encrypted backups (mounted volume so it survives container
# recreation). Falls back to /tmp if the volume is absent, but that is NOT durable.
PERSISTENT_BACKUP_DIR = os.environ.get('PERSISTENT_BACKUP_DIR', '/backups')
KEEP_LOCAL_ENCRYPTED = int(os.environ.get('KEEP_LOCAL_ENCRYPTED', '7'))


def _get_encryption_key():
    """Returns the backup encryption key or raises if missing/insecure (SCRUM-251, fail-fast)."""
    key = os.environ.get('BACKUP_ENCRYPTION_KEY')
    if not key or key == 'default_key':
        raise RuntimeError(
            "BACKUP_ENCRYPTION_KEY is not set (or left at the insecure default). "
            "Refusing to produce an unencrypted off-site backup."
        )
    return key


def _encrypt_file_aes256(src_path, key):
    """Encrypts src_path with AES-256-CBC (openssl, pbkdf2). Returns the .enc path."""
    enc_path = src_path + '.enc'
    cmd = [
        'openssl', 'enc', '-aes-256-cbc', '-salt', '-pbkdf2', '-iter', '200000',
        '-in', src_path, '-out', enc_path, '-pass', 'env:BACKUP_ENCRYPTION_KEY',
    ]
    env = dict(os.environ, BACKUP_ENCRYPTION_KEY=key)
    res = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if res.returncode != 0:
        raise RuntimeError(f"openssl encryption failed: {res.stderr}")
    return enc_path


def _split_file(path, chunk_bytes=TELEGRAM_MAX_PART_BYTES):
    """Splits path into <= chunk_bytes parts. Returns list of part paths (single item if small)."""
    size = os.path.getsize(path)
    if size <= chunk_bytes:
        return [path]
    parts = []
    with open(path, 'rb') as f:
        idx = 1
        while True:
            data = f.read(chunk_bytes)
            if not data:
                break
            part_path = f"{path}.part{idx:03d}"
            with open(part_path, 'wb') as pf:
                pf.write(data)
            parts.append(part_path)
            idx += 1
    return parts


def _telegram_send_document(bot_token, chat_id, file_path, caption=None):
    """Uploads a single file to Telegram via sendDocument. Raises on failure."""
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    with open(file_path, 'rb') as fh:
        files = {'document': (os.path.basename(file_path), fh)}
        data = {'chat_id': chat_id}
        if caption:
            data['caption'] = caption
        resp = requests.post(url, data=data, files=files, timeout=300)
    if resp.status_code != 200:
        raise RuntimeError(f"Telegram sendDocument failed ({resp.status_code}): {resp.text}")


def _rotate_local_encrypted(instance_db_name):
    """Keep only the latest KEEP_LOCAL_ENCRYPTED encrypted backups for an instance."""
    try:
        if not os.path.isdir(PERSISTENT_BACKUP_DIR):
            return
        prefix = f"backup_{instance_db_name}_"
        files = sorted(
            (f for f in os.listdir(PERSISTENT_BACKUP_DIR)
             if f.startswith(prefix) and f.endswith('.enc')),
            key=lambda f: os.path.getmtime(os.path.join(PERSISTENT_BACKUP_DIR, f)),
        )
        for old in files[:-KEEP_LOCAL_ENCRYPTED]:
            try:
                os.remove(os.path.join(PERSISTENT_BACKUP_DIR, old))
            except OSError:
                pass
    except Exception:
        pass

@shared_task
def backup_all_databases():
    """Iterates through all active DatabaseInstances and triggers a backup for each."""
    instances = DatabaseInstance.objects.filter(is_deleted=False)
    for instance in instances:
        backup_single_database.delay(instance.id)

@shared_task
def backup_single_database(instance_id):
    """pg_dump a database, persist an AES-256-encrypted copy, and ship it off-site to Telegram.

    SCRUM-251: the plaintext dump is written to a persistent volume (/backups by default),
    encrypted in place, optionally mirrored to Telegram via sendDocument (chunked >50MB), and the
    plaintext is always removed. The encrypted local copy is retained (rotated to last N) so
    backups survive a container restart.
    """
    backup_path = None
    local_enc_path = None
    try:
        instance = DatabaseInstance.objects.get(id=instance_id)
        server = instance.server

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"backup_{instance.db_name}_{timestamp}.dump"

        # Plaintext dump goes to the persistent volume (not /tmp) so it survives restarts.
        os.makedirs(PERSISTENT_BACKUP_DIR, exist_ok=True)
        backup_path = os.path.join(PERSISTENT_BACKUP_DIR, backup_filename)

        backup_record = DatabaseBackup.objects.create(
            instance=instance,
            s3_path=f"file://{backup_path}.enc",
            status='in_progress'
        )

        os.environ['PGPASSWORD'] = server.root_password
        command = [
            'pg_dump',
            '-h', server.host,
            '-p', str(server.port),
            '-U', server.root_user,
            '-F', 'c',  # Custom format for pg_restore
            '-f', backup_path,
            instance.db_name
        ]
        result = subprocess.run(command, capture_output=True, text=True)

        if result.returncode != 0:
            backup_record.status = 'failed'
            backup_record.save()
            logger.error(f"pg_dump failed for {instance.db_name}: {result.stderr}")
            return

        backup_record.file_size_bytes = os.path.getsize(backup_path)
        backup_record.save()

        # Encrypt (persist locally) + upload to Telegram. Raises on hard failure.
        local_enc_path = ship_encrypted_backup(backup_record.id, backup_path)
        _rotate_local_encrypted(instance.db_name)

        backup_record.status = 'completed'
        backup_record.save()

    except DatabaseInstance.DoesNotExist:
        pass
    except Exception as e:
        logger.error(f"Backup failed: {str(e)}")
        try:
            backup_record.status = 'failed'
            backup_record.save()
        except Exception:
            pass
    finally:
        # Always remove the plaintext dump (the .enc copy is retained on the volume).
        if backup_path and os.path.exists(backup_path):
            try:
                os.remove(backup_path)
            except OSError:
                pass


def ship_encrypted_backup(backup_id, dump_path):
    """Encrypts dump_path (AES-256) into the persistent volume and mirrors it to Telegram.

    Returns the local .enc path (kept on the volume). Raises on encryption failure so the caller
    marks the backup failed (no silent success). Telegram upload is attempted if configured; a
    Telegram failure is logged but does NOT fail the local encrypted copy.
    """
    backup = DatabaseBackup.objects.get(id=backup_id)
    instance = backup.instance
    enc_path = dump_path + '.enc'

    key = _get_encryption_key()
    enc_path = _encrypt_file_aes256(dump_path, key)

    telegram_bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    telegram_chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if telegram_bot_token and telegram_chat_id:
        try:
            parts = _split_file(enc_path)
            total = len(parts)
            for i, part in enumerate(parts, start=1):
                caption = (
                    f"🔒 Nidhi encrypted backup\n"
                    f"DB: {instance.db_name} @ {instance.server.name}\n"
                    f"{backup.created_at.strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
                    f"AES-256-CBC (openssl pbkdf2) — part {i}/{total}"
                )
                _telegram_send_document(telegram_bot_token, telegram_chat_id, part, caption=caption)
            logger.info(f"Encrypted backup for {instance.db_name} mirrored to Telegram in {total} part(s).")
            for p in parts:
                if p != enc_path and os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
        except Exception as e:
            logger.error(f"Telegram upload failed (local encrypted copy retained): {str(e)}")
    else:
        logger.warning("Telegram credentials not configured; keeping on-server encrypted backup only.")

    return enc_path


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
def check_stale_heartbeats():
    """SCRUM-260: alert on instances that have stopped reporting heartbeats.

    A missing heartbeat (app down, or app started ignoring Nidhi entirely) is as important as a
    fingerprint mismatch. Alerts once per stale episode.
    """
    from .models import InstanceHeartbeat, SystemAlert
    from django.utils import timezone as tz

    STALE_AFTER = timedelta(hours=6)
    now = tz.now()
    stale = 0
    for hb in InstanceHeartbeat.objects.select_related('instance', 'instance__server').all():
        if hb.instance.is_deleted:
            continue
        if hb.last_heartbeat_at is None:
            continue
        if now - hb.last_heartbeat_at > STALE_AFTER and not hb.stale_alerted:
            msg = (
                f"⚠️ *Nidhi Heartbeat Missing*\n"
                f"Instance `{hb.instance.db_name}` has not reported a heartbeat since "
                f"{hb.last_heartbeat_at.isoformat()}. The app may be down or bypassing Nidhi."
            )
            send_telegram_alert(msg)
            SystemAlert.objects.create(
                title=f"Heartbeat Missing: {hb.instance.db_name}",
                message=msg,
                level="warning",
            )
            hb.stale_alerted = True
            hb.save(update_fields=['stale_alerted'])
            stale += 1
    logger.info(f"Stale-heartbeat check complete: {stale} new alert(s).")
    return stale


@shared_task
def refresh_delayed_replicas():
    """SCRUM-250: maintain a ~24h-behind delayed replica for every active instance.

    Runs once daily. For each available instance it (re)builds a *stable* database named
    `{db_name}_delayed_replica` on the SAME server from a fresh dump. Because it only refreshes
    once per day, the replica always lags the primary by up to 24h — so accidental data
    destruction/corruption on the primary is NOT immediately propagated, giving a recovery window.
    """
    instances = DatabaseInstance.objects.filter(is_deleted=False, status='available')
    count = 0
    for instance in instances:
        if instance.db_name.endswith('_delayed_replica'):
            continue  # never replicate a replica
        refresh_single_delayed_replica.delay(str(instance.id))
        count += 1
    logger.info(f"Queued delayed-replica refresh for {count} instance(s).")
    return count


@shared_task
def refresh_single_delayed_replica(instance_id):
    """Rebuilds `{db_name}_delayed_replica` on the instance's server from a fresh dump."""
    import psycopg2
    from psycopg2 import sql

    dump_path = None
    try:
        instance = DatabaseInstance.objects.get(id=instance_id)
        server = instance.server
        replica_name = f"{instance.db_name}_delayed_replica"

        # Guard against low disk on /tmp before dumping.
        st = os.statvfs('/tmp')
        free_bytes = st.f_bavail * st.f_frsize
        if free_bytes < 500 * 1024 * 1024:  # <500MB free
            msg = (f"⚠️ *Nidhi delayed-replica skipped*\n`{instance.db_name}`: only "
                   f"{free_bytes // (1024*1024)}MB free on /tmp.")
            send_telegram_alert(msg)
            logger.error(msg)
            return None

        # 1. Dump the primary.
        dump_path = os.path.join('/tmp', f"delayed_{instance.db_name}_{datetime.now().strftime('%s')}.dump")
        os.environ['PGPASSWORD'] = server.root_password
        dump_cmd = [
            'pg_dump', '-h', server.host, '-p', str(server.port),
            '-U', server.root_user, '-F', 'c', '-f', dump_path, instance.db_name
        ]
        dump_res = subprocess.run(dump_cmd, capture_output=True, text=True)
        if dump_res.returncode != 0:
            raise RuntimeError(f"pg_dump failed for {instance.db_name}: {dump_res.stderr}")

        # 2. Drop + recreate the stable replica DB (terminate connections first).
        conn = psycopg2.connect(dbname="postgres", user=server.root_user,
                                password=server.root_password, host=server.host, port=server.port)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
            [replica_name],
        )
        cur.execute(sql.SQL("DROP DATABASE IF EXISTS {db}").format(db=sql.Identifier(replica_name)))
        cur.execute(sql.SQL("CREATE DATABASE {db}").format(db=sql.Identifier(replica_name)))
        cur.close()
        conn.close()

        # 3. Restore the dump into the replica.
        os.environ['PGPASSWORD'] = server.root_password
        restore_cmd = [
            'pg_restore', '-h', server.host, '-p', str(server.port),
            '-U', server.root_user, '-d', replica_name, '-O', '-x', dump_path
        ]
        restore_res = subprocess.run(restore_cmd, capture_output=True, text=True)
        if restore_res.returncode != 0:
            # pg_restore commonly exits non-zero on benign warnings (e.g. a newer client emitting
            # SET options an older server ignores). Don't trust the exit code alone — verify the
            # replica actually got populated below.
            logger.warning(f"pg_restore returned {restore_res.returncode} for {replica_name}: "
                           f"{restore_res.stderr.strip()[:500]}")

        # Verify the restore by confirming the replica has objects in the public schema.
        vconn = psycopg2.connect(dbname=replica_name, user=server.root_user,
                                 password=server.root_password, host=server.host, port=server.port)
        vcur = vconn.cursor()
        vcur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
        table_count = vcur.fetchone()[0]
        vcur.close()
        vconn.close()
        if table_count == 0:
            raise RuntimeError(f"pg_restore produced an empty replica {replica_name} "
                               f"(0 public tables). stderr: {restore_res.stderr.strip()[:500]}")

        logger.info(f"Delayed replica refreshed: {replica_name} "
                    f"({table_count} tables, as of {timezone.now().isoformat()}).")
        return replica_name

    except DatabaseInstance.DoesNotExist:
        return None
    except Exception as e:
        logger.error(f"Delayed replica refresh failed: {str(e)}")
        send_telegram_alert(f"⚠️ *Nidhi delayed-replica FAILED* for instance `{instance_id}`: {str(e)}")
        return None
    finally:
        if dump_path and os.path.exists(dump_path):
            try:
                os.remove(dump_path)
            except OSError:
                pass


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
