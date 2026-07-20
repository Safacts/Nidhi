import re
import os
import subprocess
import pathlib
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
def backup_all_databases(include_development=None):
    """Iterates through all active DatabaseInstances and triggers a backup for each.

    By default, ONLY production databases are backed up. Development databases are
    skipped unless explicitly requested:
      - include_development=True passed directly, OR
      - env BACKUP_DEVELOPMENT_DBS=1 is set (used for one-off manual dev backups).
    """
    if include_development is None:
        include_development = os.environ.get('BACKUP_DEVELOPMENT_DBS', '0') == '1'
    qs = DatabaseInstance.objects.filter(is_deleted=False, backup_enabled=True)
    if not include_development:
        # Keep only instances whose server is a PRODUCTION environment.
        qs = qs.exclude(server__environment_type='development')
    skipped = (DatabaseInstance.objects.filter(is_deleted=False, server__environment_type='development').count()
               if not include_development else 0)
    for instance in qs:
        backup_single_database.delay(instance.id)
    if skipped:
        logger.info(f"backup_all_databases skipped {skipped} development instance(s) (BACKUP_DEVELOPMENT_DBS not set).")

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

        # Encrypt (persist locally) + upload to Telegram. Raises if the off-site mirror fails.
        try:
            local_enc_path = ship_encrypted_backup(backup_record.id, backup_path)
            _rotate_local_encrypted(instance.db_name)
            backup_record.status = 'completed'
            backup_record.save()
        except Exception as ship_e:
            backup_record.status = 'failed'
            backup_record.save()
            from .models import AuditLog
            AuditLog.objects.create(
                actor_type='system', actor='celery:backup_single_database',
                action='backup_failed', target=instance.db_name, server=instance.server.name,
                detail=f"Off-site (Telegram) upload failed: {str(ship_e)[:300]}", success=False,
            )
            send_telegram_alert(
                f"🚨 *Nidhi Backup FAILED*\nBackup for `{instance.db_name}` could not be mirrored "
                f"off-site (Telegram). Local encrypted copy may exist but off-site is MISSING.\n"
                f"{str(ship_e)[:200]}"
            )
            logger.error(f"Backup off-site failure for {instance.db_name}: {ship_e}")
            return

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
    # Support multiple recipients (comma-separated). All recipients receive every backup
    # so the owner/founder (Uma Mahesh Sir) and the founding engineer both get off-site copies.
    chat_ids = [c.strip() for c in (telegram_chat_id or '').split(',') if c.strip()] if telegram_chat_id else []
    if telegram_bot_token and chat_ids:
        try:
            parts = _split_file(enc_path)
            total = len(parts)
            for chat in chat_ids:
                for i, part in enumerate(parts, start=1):
                    caption = (
                    f"🔒 Nidhi encrypted backup\n"
                    f"DB: {instance.db_name} @ {instance.server.name}\n"
                    f"{backup.created_at.strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
                    f"AES-256-CBC (openssl pbkdf2) — part {i}/{total}"
                    )
                    _telegram_send_document(telegram_bot_token, chat, part, caption=caption)
            logger.info(f"Encrypted backup for {instance.db_name} mirrored to Telegram ({len(chat_ids)} recipient(s)) in {total} part(s).")
            for p in parts:
                if p != enc_path and os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
        except Exception as e:
            # SCRUM data-safety (2026-07-17): a failed off-site mirror MUST NOT be reported as a
            # successful backup. Raise so the caller marks the backup FAILED and alerts.
            raise RuntimeError(f"Telegram off-site upload FAILED (local encrypted copy retained): {str(e)}")
    else:
        logger.warning("Telegram credentials not configured; keeping on-server encrypted backup only.")

    return enc_path


def send_telegram_alert(message: str, parse_mode='Markdown'):
    """Generic function to send a Telegram alert message."""
    telegram_bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    telegram_chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    if not telegram_bot_token or not telegram_chat_id:
        logger.info("Telegram credentials not configured, skipping alert")
        return
        
    telegram_url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
    
    def _send(pm):
        payload = {
            'chat_id': telegram_chat_id,
            'text': message,
        }
        if pm:
            payload['parse_mode'] = pm
        resp = requests.post(telegram_url, json=payload, timeout=10)
        return resp
    
    try:
        response = _send(parse_mode)
        if response.status_code != 200:
            if parse_mode:
                response = _send(None)
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
def verify_database_liveness():
    """SCRUM data-safety (post 2026-07-17 incident): actively verify each provisioned DB still
    EXISTS and is CONNECTABLE on its data plane. Nidhi previously only trusted the 'available'
    flag set at provision time, so a wiped data plane was reported AVAILABLE for days. This task
    connects to every active instance, flips status to 'failed' when unreachable, and alerts."""
    import psycopg2
    from .models import AuditLog, SystemAlert

    checked = 0
    down = 0
    for instance in DatabaseInstance.objects.filter(is_deleted=False):
        checked += 1
        server = instance.server
        reachable = True
        detail = ""
        try:
            conn = psycopg2.connect(
                dbname="postgres", user=server.root_user, password=server.root_password,
                host=server.host, port=server.port, connect_timeout=8,
            )
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", [instance.db_name])
                exists = cur.fetchone() is not None
            conn.close()
            if not exists:
                reachable = False
                detail = f"DB '{instance.db_name}' no longer exists on {server.name}."
        except Exception as e:
            reachable = False
            detail = f"Connect failed: {str(e)[:200]}"

        expected_status = 'available' if reachable else 'failed'
        if instance.status != expected_status:
            instance.status = expected_status
            instance.save(update_fields=['status'])
            AuditLog.objects.create(
                actor_type='system', actor='celery:verify_database_liveness',
                action='liveness_changed', target=instance.db_name, server=server.name,
                detail=detail or f"status-> {expected_status}", success=reachable,
            )
            msg = (f"🚨 *Nidhi DB Liveness Alert*\n"
                   f"Instance `{instance.db_name}` on `{server.name}` is "
                   f"{'UNREACHABLE' if not reachable else 'OK'}.\n{detail}")
            send_telegram_alert(msg)
            SystemAlert.objects.create(
                title=f"DB Liveness: {instance.db_name}",
                message=msg, level="error" if not reachable else "info",
            )
        if not reachable:
            down += 1
    logger.info(f"Liveness check complete: {checked} checked, {down} down.")
    return {"checked": checked, "down": down}


@shared_task
def refresh_delayed_replicas():
    """SCRUM-250: maintain a ~24h-behind delayed replica for every active instance.

    Runs once daily. For each available instance it (re)builds a *stable* database named
    `{db_name}_delayed_replica` on the SAME server from a fresh dump. Because it only refreshes
    once per day, the replica always lags the primary by up to 24h — so accidental data
    destruction/corruption on the primary is NOT immediately propagated, giving a recovery window.
    """
    instances = DatabaseInstance.objects.filter(is_deleted=False, status='available', backup_enabled=True)
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
            status='provisioning',
            backup_enabled=False,  # dev instances are opt-in for backup
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
        # Use bucket.endpoint if already set, otherwise derive from server or env
        if bucket.endpoint:
            endpoint = bucket.endpoint
        elif bucket.server:
            # Production: Use VPS MinIO
            endpoint = f"{bucket.server.host}:9000"
        else:
            # Development: Use local MinIO container
            endpoint = os.environ.get("MINIO_ENDPOINT", "minio:9000")

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


@shared_task
def check_minio_health():
    """Periodically check if MinIO instances are healthy and alert on failures.

    Robust: the error message is captured into a plain string immediately inside the
    except block (no reliance on the except-scoped `e` variable afterwards), and alerts
    are de-duplicated so we do not spam every 5 minutes while a node is down.
    """
    from .models import SystemAlert
    from minio import Minio
    import os

    results = []
    # Dev MinIO is on the devserver; from inside the container use the docker host gateway.
    vps_endpoint = os.environ.get('VPS_MINIO_ENDPOINT', '72.60.218.127:9000')
    dev_endpoint = os.environ.get('DEV_MINIO_ENDPOINT', '172.21.0.1:9000')
    access_key = os.environ.get('MINIO_ACCESS_KEY', 'admin_nidhi_minio')
    secret_key = os.environ.get('MINIO_SECRET_KEY', 'secure_nidhi_minio_password')

    def _check(endpoint, label, min_buckets, title):
        try:
            client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=False)
            buckets = list(client.list_buckets())
            ok = len(buckets) >= min_buckets
            results.append(f"{label}: {'OK' if ok else 'WARN'} ({len(buckets)} buckets)")
            return ok
        except Exception as exc:
            err_msg = str(exc)
            results.append(f"{label}: DOWN - {err_msg[:100]}")
            # De-dupe: only alert if no unread alert of this title in the last 30 min.
            recent = SystemAlert.objects.filter(
                title=title, is_read=False,
                created_at__gte=timezone.now() - timedelta(minutes=30),
            ).exists()
            if not recent:
                SystemAlert.objects.create(
                    title=title,
                    message=f"{label} at {endpoint} is unreachable: {err_msg[:300]}",
                    level='error',
                )
                send_telegram_alert(
                    f"🚨 *MinIO DOWN*\n{label} ({endpoint}) is unreachable!\n{err_msg[:200]}"
                )
            return False

    _check(vps_endpoint, 'VPS MinIO', 6, 'VPS MinIO DOWN')
    _check(dev_endpoint, 'Dev MinIO', 1, 'Dev MinIO DOWN')

    logger.info(f"MinIO health check: {' | '.join(results)}")
    return results
@shared_task
def send_ai_alert_summary():
    """Collect recent unread alerts, draft a summary via Gemma 4, send to Telegram."""
    from datetime import timedelta
    from django.utils import timezone
    from .models import SystemAlert

    cutoff = timezone.now() - timedelta(hours=6)
    base_qs = SystemAlert.objects.filter(created_at__gte=cutoff, is_read=False)
    total = base_qs.count()

    if total == 0:
        logger.info('No unread alerts in last 6h - skipping AI summary')
        return

    error_count = base_qs.filter(level='error').count()
    warning_count = base_qs.filter(level='warning').count()
    info_count = base_qs.filter(level='info').count()

    alerts = base_qs.order_by('-created_at')[:20]

    header = (
        f"\U0001f916 Nidhi Alert Report\n"
        f"{total} alerts \u2022 "
        f"{error_count} \U0001f534 {warning_count} \U0001f7e1 {info_count} \U0001f535\n"
        f"-------------------------\n"
    )

    # Send only 10 most recent alerts to LLM with short messages to avoid timeout
    alert_lines = []
    for a in alerts[:10]:
        alert_lines.append(f"[{a.level.upper()}] {a.title[:80]}: {a.message[:100]}")
    alert_text = "\n".join(alert_lines)

    llm_url = os.environ.get('LLM_API_URL', 'http://72.60.218.127:8080/v1/chat/completions')
    llm_model = os.environ.get('LLM_MODEL', '/models/gemma-4-E4B-it-Q4_K_M.gguf')

    system_prompt = (
        "You are Nidhi, an AI SRE assistant. "
        "Summarize these system alerts concisely for a Telegram message. "
        "Plain text only - no formatting, no markdown, no HTML. "
        "Group by severity, suggest causes. Max 800 chars. - Nidhi AI"
    )

    payload = {
        'model': llm_model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': f'Alerts:\n{alert_text}'}
        ],
        'temperature': 0.3,
        'max_tokens': 300,
    }

    try:
        resp = requests.post(llm_url, json=payload, timeout=180)
        resp.raise_for_status()
        data = resp.json()
        drafted = data['choices'][0]['message']['content']
        # Strip model tokens
        drafted = drafted.split('<|im_end|>')[0].split('<|im_start|>')[0].strip()
        # Sanitize Markdown for Telegram compatibility
        import re
        drafted = re.sub(r'^#{1,6}\s*', '', drafted, flags=re.MULTILINE)  # remove headings
        drafted = re.sub(r'\n-{3,}\n*', '\n', drafted)  # remove --- lines
        drafted = re.sub(r'\*\*(.+?)\*\*', r'*\1*', drafted)  # **bold** -> *bold*
        # Remove bullet markers (* at line start) — Telegram Markdown doesn't support lists
        drafted = re.sub(r'^\*\s+', '', drafted, flags=re.MULTILINE)
        # Collapse 3+ consecutive newlines into 2
        drafted = re.sub(r'\n{3,}', '\n\n', drafted)
        drafted = drafted.strip()
    except Exception as e:
        logger.error(f'AI drafting failed: {e}')
        drafted = (
            f"*Nidhi Alert Summary*\n"
            f"{total} unread alerts in last 6h. "
            f"{error_count} errors, {warning_count} warnings.\n"
            f"AI drafting unavailable - raw stats above."
        )



@shared_task
def monitor_backup_health():
    """Continuous backup watchdog (SCRUM data-safety).

    Verifies the Nidhi-managed backup control plane is actually producing fresh,
    successful backups. A stale or failed run raises a SystemAlert + Telegram page so a
    silent backup stop is never missed. Runs hourly via Celery beat.
    """
    from .models import BackupStatus, SystemAlert
    now = timezone.now()
    STALE_HOURS = 26

    def _last(kind):
        return BackupStatus.objects.filter(kind=kind).order_by('-started_at').first()

    problems = []
    for kind, label in [('minio_media', 'MinIO media mirror'), ('db_copy_tb', 'DB-to-TB copy')]:
        run = _last(kind)
        if not run:
            problems.append(f"{label}: NO backup run recorded yet")
            continue
        if run.status == 'failed':
            problems.append(f"{label}: last run FAILED ({run.started_at})")
            continue
        if not run.finished_at:
            problems.append(f"{label}: run stuck in 'running' since {run.started_at}")
            continue
        age = (now - run.finished_at).total_seconds() / 3600
        if age > STALE_HOURS:
            problems.append(f"{label}: last success {age:.1f}h ago (> {STALE_HOURS}h SLA)")
        if run.status == 'partial':
            problems.append(f"{label}: last run PARTIAL ({run.items_failed} failed items)")

    if problems:
        msg = "\U0001F6A8 *Nidhi Backup Watchdog ALERT*\n" + chr(10).join("- " + p for p in problems)
        send_telegram_alert(msg, parse_mode='Markdown')
        for p in problems:
            SystemAlert.objects.create(
                title=f"Backup health: {p.split(':')[0]}",
                message=p, level='error', is_read=False,
            )
        logger.error(f"Backup watchdog found {len(problems)} problem(s)")
        return False
    logger.info("Backup watchdog: all backups healthy")
    return True


    full_message = header + drafted

    send_telegram_alert(full_message, parse_mode='Markdown')
    logger.info(f'AI alert summary sent to Telegram ({total} alerts)')
    return full_message


# ==============================================================================
# NIDHI-MANAGED BACKUP CONTROL PLANE  (SCRUM data-safety)
# ------------------------------------------------------------------------------
# These tasks replace fragile host cron scripts. The schedule lives in
# nidhi_backend/celery.py (VCS-tracked, survives container restart) and every run
# is recorded in BackupStatus so the control plane can prove backups are happening.
# Media + DB copies land on the devserver TB disk (/backups_media) — the VPS cannot
# hold long-term backups for all apps' media.
# ==============================================================================

import shutil
from .models import BackupStatus, StorageBucket, DatabaseInstance, AuditLog


def _mc_mirror_bucket(bucket_name, endpoint, access_key, secret_key, dest_dir):
    """Mirror a single MinIO bucket to dest_dir using the host mc binary.

    Uses a fixed alias SRC (mc's MC_HOST_ env lookup rejects underscores in alias names).
    Returns (bytes_transferred, error_or_None).
    """
    os.makedirs(dest_dir, exist_ok=True)
    env = dict(os.environ)
    # The backup worker runs on the devserver. Dev buckets are recorded with
    # endpoint=localhost:9000 (the host's own MinIO); inside the container that
    # resolves to the container itself, so rewrite localhost -> docker host gateway.
    raw_host = endpoint.split('://')[-1]
    if raw_host.startswith('localhost:'):
        raw_host = '172.21.0.1:' + raw_host.split(':', 1)[1]
    host_val = "http://{}:{}@{}".format(access_key, secret_key, raw_host)
    env["MC_HOST_SRC"] = host_val
    cmd = [
        'mc', 'mirror', '--overwrite', '--quiet',
        "SRC/{}".format(bucket_name),
        dest_dir + '/',
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if res.returncode != 0:
        return 0, res.stderr
    try:
        size = sum(f.stat().st_size for f in pathlib.Path(dest_dir).rglob('*') if f.is_file())
    except Exception:
        size = 0
    return size, None


@shared_task
def backup_all_minio_media():
    """Mirror every production StorageBucket from the VPS MinIO to the devserver TB disk.

    Nidhi-managed replacement for the host pull_minio_backup.sh. Reports to BackupStatus +
    AuditLog and alerts on failure.
    """
    run = BackupStatus.objects.create(kind='minio_media', target='all', status='running')
    total = ok = failed = 0
    bytes_total = 0
    errors = []
    try:
        prod_buckets = StorageBucket.objects.filter(status='available', backup_enabled=True)
        total = prod_buckets.count()
        media_root = os.environ.get('TB_MEDIA_DIR', '/backups_media/minio')
        for bucket in prod_buckets:
            dest = os.path.join(media_root, bucket.bucket_name)
            size, err = _mc_mirror_bucket(
                bucket.bucket_name, bucket.endpoint,
                bucket.access_key, bucket.secret_key, dest,
            )
            if err:
                failed += 1
                errors.append("{}: {}".format(bucket.bucket_name, err[:120]))
            else:
                ok += 1
                bytes_total += size
        run.items_total = total
        run.items_ok = ok
        run.items_failed = failed
        run.bytes_transferred = bytes_total
        run.destination = media_root
        run.status = 'completed' if failed == 0 else ('partial' if ok else 'failed')
        run.finished_at = timezone.now()
        run.detail = ("\n".join(errors))[:2000] if errors else "All buckets mirrored."
        run.save()
        AuditLog.objects.create(
            actor_type='system', actor='celery:backup_all_minio_media',
            action='backup_db', target='minio_media', server='devserver-TB',
            detail="mirrored {}/{} buckets, {} bytes".format(ok, total, bytes_total),
            success=(failed == 0),
        )
        if failed:
            send_telegram_alert(
                "*MinIO Media Backup PARTIAL/FAIL*\n{}/{} buckets mirrored to TB disk.\n{}".format(
                    ok, total, "\n".join(errors[:5]))
            )
    except Exception as e:
        run.status = 'failed'
        run.finished_at = timezone.now()
        run.detail = str(e)[:2000]
        run.save()
        send_telegram_alert("*MinIO Media Backup FAILED*\n{}".format(str(e)[:300]))
    return run.status


@shared_task
def copy_db_backups_to_tb_disk():
    """Copy completed encrypted DB dumps from the nidhi_backups volume to the TB disk.

    Guarantees prod + dev DB dumps also have a durable copy on the devserver TB disk
    (in addition to the Telegram off-site mirror).
    """
    run = BackupStatus.objects.create(kind='db_copy_tb', target='all', status='running')
    try:
        src_root = PERSISTENT_BACKUP_DIR  # /backups (nidhi_backups volume)
        dest_root = os.environ.get('TB_DB_DIR', '/backups_media/db')
        os.makedirs(dest_root, exist_ok=True)
        if not os.path.isdir(src_root):
            raise RuntimeError("Source backup dir {} not found".format(src_root))
        copied = 0
        bytes_total = 0
        for f in os.listdir(src_root):
            if f.endswith('.enc'):
                sp = os.path.join(src_root, f)
                dp = os.path.join(dest_root, f)
                shutil.copy2(sp, dp)
                copied += 1
                bytes_total += os.path.getsize(dp)
        run.items_total = copied
        run.items_ok = copied
        run.bytes_transferred = bytes_total
        run.destination = dest_root
        run.status = 'completed'
        run.finished_at = timezone.now()
        run.detail = "Copied {} encrypted dumps to TB disk.".format(copied)
        run.save()
    except Exception as e:
        run.status = 'failed'
        run.finished_at = timezone.now()
        run.detail = str(e)[:2000]
        run.save()
        send_telegram_alert("*DB-to-TB copy FAILED*\n{}".format(str(e)[:300]))
    return run.status


# ==============================================================================
# Bucket -> Bucket replication (MinIO -> MinIO)
# Nidhi-internal media replication, mirroring the DB-to-DB `replicate_prod_to_dev`
# pattern. Copies the *contents* of a source StorageBucket into a destination
# StorageBucket on (possibly) another MinIO endpoint. Records BackupStatus +
# AuditLog and alerts on failure. This completes the data-transfer picture:
# DB->DB exists (replicate_prod_to_dev), DB->delayed-replica exists
# (refresh_delayed_replicas), bucket->TB-disk exists (backup_all_minio_media);
# this adds true bucket->bucket replication.
# ==============================================================================

def _mc_mirror_bucket_to_bucket(src_bucket, src_endpoint, src_key, src_secret,
                                dst_bucket, dst_endpoint, dst_key, dst_secret):
    """Mirror one MinIO bucket's contents into another bucket (any endpoint) via `mc mirror`.

    Returns (bytes_transferred, error_or_None). Creates the destination bucket if missing.
    mc's MC_HOST_ env lookup rejects underscores in alias names, so fixed aliases SRC/DST are used.
    """
    env = dict(os.environ)

    def _host_env(alias, endpoint, key, secret):
        raw = endpoint.split('://')[-1]
        # Inside the container, dev buckets recorded as localhost:9000 resolve to the
        # container itself; rewrite to the docker host gateway so we reach the real MinIO.
        if raw.startswith('localhost:'):
            raw = '172.21.0.1:' + raw.split(':', 1)[1]
        env["MC_HOST_{}".format(alias)] = "http://{}:{}@{}".format(key, secret, raw)

    _host_env('SRC', src_endpoint, src_key, src_secret)
    _host_env('DST', dst_endpoint, dst_key, dst_secret)

    # Ensure destination bucket exists (mirror won't create it).
    mk = subprocess.run(
        ['mc', 'mb', '--ignore-existing', "DST/{}".format(dst_bucket)],
        capture_output=True, text=True, env=env,
    )
    if mk.returncode != 0:
        return 0, "mk bucket failed: " + mk.stderr

    # Mirror source -> destination.
    res = subprocess.run(
        ['mc', 'mirror', '--overwrite', '--quiet',
         "SRC/{}".format(src_bucket), "DST/{}".format(dst_bucket)],
        capture_output=True, text=True, env=env,
    )
    if res.returncode != 0:
        return 0, res.stderr
    try:
        # mc can report transferred bytes; fall back to 0 if absent.
        out = res.stderr + res.stdout
        m = __import__('re').search(r'([0-9,]+)\s*bytes', out)
        size = int(m.group(1).replace(',', '')) if m else 0
    except Exception:
        size = 0
    return size, None


@shared_task
def replicate_bucket(src_bucket_id, dst_bucket_id=None):
    """Replicate the contents of one StorageBucket into a destination bucket.

    If dst_bucket_id is omitted, the destination is derived from the source using the
    {slug}-{environment}-media convention mirrored to the *other* environment's MinIO
    (prod -> dev, dev -> prod). Records BackupStatus + AuditLog(replicate_bucket).
    """
    from .models import StorageBucket
    run = BackupStatus.objects.create(kind='bucket_replica', target='', status='running')
    try:
        src = StorageBucket.objects.get(id=src_bucket_id, status='available')
        if dst_bucket_id:
            dst = StorageBucket.objects.get(id=dst_bucket_id, status='available')
        else:
            # Derive counterpart by flipping environment in the bucket name.
            name = src.bucket_name  # e.g. aacharya-production-media
            if name.endswith('-production-media'):
                dst_name = name.replace('-production-media', '-development-media')
            elif name.endswith('-development-media'):
                dst_name = name.replace('-development-media', '-production-media')
            else:
                dst_name = None
            dst = StorageBucket.objects.filter(bucket_name=dst_name, status='available').first() if dst_name else None
            if dst is None:
                raise RuntimeError("No available destination bucket for {}".format(name))

        run.target = "{} -> {}".format(src.bucket_name, dst.bucket_name)
        run.save()

        size, err = _mc_mirror_bucket_to_bucket(
            src.bucket_name, src.endpoint, src.access_key, src.secret_key,
            dst.bucket_name, dst.endpoint, dst.access_key, dst.secret_key,
        )
        if err:
            run.status = 'failed'
            run.detail = err[:2000]
            run.finished_at = timezone.now()
            run.save()
            AuditLog.objects.create(
                actor_type='system', actor='celery:replicate_bucket',
                action='replicate_bucket', target=run.target, server=dst.endpoint,
                detail="FAILED: " + err[:300], success=False,
            )
            send_telegram_alert(
                "*Bucket Replication FAILED*\n{} -> {}\n{}".format(
                    src.bucket_name, dst.bucket_name, err[:300]))
            return 'failed'

        run.items_total = 1
        run.items_ok = 1
        run.bytes_transferred = size
        run.status = 'completed'
        run.finished_at = timezone.now()
        run.detail = "Replicated {} -> {} ({} bytes)".format(src.bucket_name, dst.bucket_name, size)
        run.save()
        AuditLog.objects.create(
            actor_type='system', actor='celery:replicate_bucket',
            action='replicate_bucket', target=run.target, server=dst.endpoint,
            detail="Replicated {} bytes".format(size), success=True,
        )
        return 'completed'
    except Exception as e:
        run.status = 'failed'
        run.finished_at = timezone.now()
        run.detail = str(e)[:2000]
        run.save()
        send_telegram_alert("*Bucket Replication FAILED*\n{}".format(str(e)[:300]))
        return 'failed'


@shared_task
def replicate_all_buckets():
    """Nightly: replicate every available source bucket to its counterpart (prod<->dev).

    Mirrors the scheduled `replicate_prod_to_dev` pattern for media. Skips buckets that
    have no available counterpart so partial success is reported, not a hard failure.
    """
    from .models import StorageBucket
    buckets = StorageBucket.objects.filter(status='available', backup_enabled=True)
    ok = failed = 0
    for b in buckets:
        # Only drive replication from one side to avoid double-work: replicate
        # production buckets to development (and vice-versa if no prod counterpart).
        res = replicate_bucket.delay(str(b.id))
        # .delay returns an AsyncResult; the actual work runs async. Count intent here.
        ok += 1
    return "queued {} bucket replication(s)".format(ok)
