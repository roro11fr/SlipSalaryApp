from rest_framework.permissions import BasePermission

class IsManager(BasePermission):
    def has_permission(self, request, view):
        u = getattr(request, "user", None)
        return bool(
            u and u.is_authenticated and getattr(u, "role", None) == "MANAGER" and getattr(u, "active", True)
        )
