# backend/api/permissions.py
from rest_framework.permissions import BasePermission

# For this MVP, we will trust the role sent in the request header.
# In a full production system, you would decode a JWT here.


class IsAdminUser(BasePermission):
    def has_permission(self, request, view):
        role = request.headers.get('X-User-Role', '').lower()
        return role == 'admin'

class IsAuthenticatedUser(BasePermission):
    def has_permission(self, request, view):
        role = request.headers.get('X-User-Role', '').lower()
        # Now we allow all three valid roles
        return role in ['student', 'admin', 'faculty']