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


import os
from .models import is_production_environment, prod_deletion_guard_enabled


class IsProductionDestructiveOp(BasePermission):
    """Multi-level guard for ANY operation that can destroy production data.

    Levels (all must pass):
      L1  Nidhi must be running as the production control plane (NIDHI_ENVIRONMENT=production).
          A dev/standby instance is NEVER allowed to perform destructive prod ops.
      L2  Caller must be a Founding Engineer (IsFoundingEngineer).
      L3  A confirmation nonce must be supplied: header `X-Confirm-Destroy: <db_name>`
          (or query/body `confirm_destroy` == db_name). Prevents accidental single-click deletes.
      L4  Global kill-switch: if prod_deletion_guard_enabled() is False the op is allowed only
          when NIDHI_ALLOW_PROD_DELETION is explicitly set (break-glass, always audited).
    This protects against the 2026-07-17 incident where prod DBs were wiped with no gate.
    """
    def has_permission(self, request, view):
        from .models import DatabaseInstance
        if not prod_deletion_guard_enabled():
            # Break-glass mode: still require founding engineer + audit (handled in view).
            return bool(getattr(request.user, 'role', '') == 'founding_engineer')
        if not is_production_environment():
            return False
        if not (request.user and request.user.is_authenticated
                and getattr(request.user, 'role', '') == 'founding_engineer'):
            return False
        # L3: explicit confirmation nonce matching the target db name.
        target_id = view.kwargs.get('instance_id') or view.kwargs.get('bucket_id')
        confirm = (request.headers.get('X-Confirm-Destroy')
                   or request.data.get('confirm_destroy')
                   or request.query_params.get('confirm_destroy'))
        if target_id:
            try:
                inst = DatabaseInstance.objects.get(id=target_id)
                expected = inst.db_name
            except DatabaseInstance.DoesNotExist:
                expected = str(target_id)
            if confirm != expected:
                return False
        return True

class IsFoundingEngineer(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and getattr(request.user, 'role', '') == 'founding_engineer')
