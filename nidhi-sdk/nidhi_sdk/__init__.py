from .fastapi import get_nidhi_storage_client, upload_file_to_nidhi, delete_file_from_nidhi, get_nidhi_database_url
from .django import inject_nidhi_storage, inject_nidhi_database
from .telegram import send_telegram_alert
from .database import get_database_fingerprint, send_heartbeat
