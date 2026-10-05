from rest_framework import permissions

from accounts.models import User


class IsAdminRole(permissions.BasePermission):
    """仅角色为「管理员」的已登录用户允许通过。"""

    message = "仅管理员可执行该操作"

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and getattr(user, "role", None) == User.ROLE_ADMIN
        )
