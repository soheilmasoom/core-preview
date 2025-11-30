from django.conf import settings
from rest_framework.permissions import IsAuthenticated, AllowAny

from accounts.models import User
from accounts.utils.hijack import get_hijacker_id


class ActionBasedPermission(AllowAny):
    """
    Grant or deny access to a view, based on a mapping in view.action_permissions
    """
    def has_permission(self, request, view):
        for klass, actions in getattr(view, 'action_permissions', {}).items():
            if view.action in actions:
                return klass().has_permission(request, view)
        return False


class IsBasicVerified(IsAuthenticated):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False

        return request.user.level >= User.LEVEL2


def can_trade(request) -> bool:
    if not settings.TRADE_ENABLE or not request.user.can_trade:
        hijacker_id = get_hijacker_id(request)
        if not hijacker_id:
            return False

        hijacker = User.objects.get(id=hijacker_id)

        if hijacker.is_superuser:
            return True
        else:
            return False

    return True
