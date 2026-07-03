from .fastapi import get_nidhi_storage_client, upload_file_to_nidhi, delete_file_from_nidhi
from .django import inject_nidhi_storage

__all__ = [
    'get_nidhi_storage_client',
    'upload_file_to_nidhi',
    'delete_file_from_nidhi',
    'inject_nidhi_storage',
]
