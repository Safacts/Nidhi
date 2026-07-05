import time
import logging
import threading
from django.conf import settings

logger = logging.getLogger(__name__)

# Track state to avoid spamming alerts. 
# db_name -> bool (True if currently in alert state)
_alert_state = {}

def monitoring_loop():
    """Runs infinitely in a background thread."""
    from .models import DatabaseInstance
    from .tasks import send_telegram_alert
    import psycopg2

    logger.info("✅ Nidhi Native Monitoring Thread Started (1-min interval)")
    
    while True:
        try:
            instances = DatabaseInstance.objects.filter(is_deleted=False, status='available')
            servers = set(instance.server for instance in instances if instance.server)
            
            for server in servers:
                try:
                    conn = psycopg2.connect(
                        dbname="postgres",
                        user=server.root_user,
                        password=server.root_password,
                        host=server.host,
                        port=server.port
                    )
                    cursor = conn.cursor()
                    cursor.execute("SELECT datname, numbackends FROM pg_stat_database")
                    stats = {row[0]: row[1] for row in cursor.fetchall()}
                    cursor.close()
                    conn.close()
                    
                    server_instances = [i for i in instances if i.server == server]
                    for instance in server_instances:
                        connections = stats.get(instance.db_name, 0)
                        
                        if connections == 0:
                            # Alert if not already in alert state
                            if not _alert_state.get(instance.db_name):
                                msg = (
                                    f"⚠️ *Nidhi Monitoring Alert*\n"
                                    f"Application database `{instance.db_name}` on server `{server.name}` "
                                    f"has **0 active connections**.\n"
                                    f"It may have fallen back to SQLite or a hardcoded database!"
                                )
                                send_telegram_alert(msg)
                                logger.warning(f"0 connections detected for {instance.db_name}. Alert sent.")
                                _alert_state[instance.db_name] = True
                        else:
                            # Recovered
                            if _alert_state.get(instance.db_name):
                                msg = (
                                    f"✅ *Nidhi Monitoring Recovery*\n"
                                    f"Application database `{instance.db_name}` has reconnected "
                                    f"({connections} active connections)."
                                )
                                send_telegram_alert(msg)
                                logger.info(f"{instance.db_name} reconnected.")
                                _alert_state[instance.db_name] = False
                                
                except Exception as e:
                    logger.error(f"Failed to monitor databases on server {server.name}: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Critical error in monitoring loop: {str(e)}")
            
        # Sleep for 60 seconds
        time.sleep(60)

def start_monitoring_thread():
    """Starts the monitoring thread if not already running."""
    thread = threading.Thread(target=monitoring_loop, daemon=True, name="NidhiMonitor")
    thread.start()
