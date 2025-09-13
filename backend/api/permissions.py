# backend/api/permissions.py
from rest_framework.permissions import BasePermission

# For this MVP, we will trust the role sent in the request header.
# In a full production system, you would decode a JWT here.

class IsAdminUser(BasePermission):
    """
    Allows access only to admin users.
    """
    def has_permission(self, request, view):
        # We expect the frontend to send the user's role in the headers
        role = request.headers.get('X-User-Role', '').lower()
        return role == 'admin'

class IsAuthenticatedUser(BasePermission):
    """
    Allows access to any authenticated user (student or admin).
    """
    def has_permission(self, request, view):
        role = request.headers.get('X-User-Role', '').lower()
        return role in ['student', 'admin']