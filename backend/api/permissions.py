# backend/api/permissions.py
from rest_framework.permissions import BasePermission

class IsAdminUser(BasePermission):
    def has_permission(self, request, view):
        role = request.headers.get('X-User-Role', '').lower()
        # This now correctly allows all admin-level roles
        return role in ['admin', 'college_admin', 'super_admin']

class IsAuthenticatedUser(BasePermission):
    def has_permission(self, request, view):
        role = request.headers.get('X-User-Role', '').lower()
        # This allows any logged-in user, regardless of role
        return role in ['student', 'admin', 'college_admin', 'super_admin', 'faculty']
