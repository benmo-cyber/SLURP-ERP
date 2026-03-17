"""
Role-based permission for ERP: Viewer (read-only), Operator, Manager, Admin.
"""
from rest_framework import permissions


def get_user_role(request):
    """Return the user's ERP role string or None if no profile."""
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return None
    try:
        profile = getattr(request.user, 'erp_profile', None)
        return profile.role if profile else None
    except Exception:
        return None


class IsAuthenticated(permissions.BasePermission):
    """Require authenticated user (session or token)."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


class IsAdmin(permissions.BasePermission):
    """Require role admin."""
    def has_permission(self, request, view):
        return get_user_role(request) == 'admin'


class IsManagerOrAdmin(permissions.BasePermission):
    """Require role manager or admin."""
    def has_permission(self, request, view):
        role = get_user_role(request)
        return role in ('manager', 'admin')


class IsOperatorOrAbove(permissions.BasePermission):
    """Require role operator, manager, or admin (not viewer-only)."""
    def has_permission(self, request, view):
        role = get_user_role(request)
        return role in ('operator', 'manager', 'admin')


def has_role(request, *roles):
    """Helper: True if current user has one of the given roles."""
    return get_user_role(request) in roles
