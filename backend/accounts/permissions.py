from rest_framework.permissions import BasePermission


class IsAdminRole(BasePermission):
    """仅 role=admin 的账户放行；操作工（worker）一律拒绝。"""

    message = "仅管理员可执行此操作"

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == user.ROLE_ADMIN)
