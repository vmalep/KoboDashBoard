from django.conf import settings
from django.contrib.auth import get_user_model


def pending_users(request):
    if request.user.is_authenticated and request.user.email in settings.POWER_USER_EMAILS:
        count = get_user_model().objects.filter(is_active=False).count()
        return {'pending_users_count': count}
    return {'pending_users_count': 0}


def user_roles(request):
    if not request.user.is_authenticated:
        return {'is_power_user': False, 'is_group_admin': False, 'site_config': _site_config()}
    from kobo.models import DashboardGroup
    is_power = request.user.email in settings.POWER_USER_EMAILS
    is_gadmin = not is_power and DashboardGroup.objects.filter(admins=request.user).exists()
    return {
        'is_power_user': is_power,
        'is_group_admin': is_gadmin,
        'site_config': _site_config(),
    }


def _site_config():
    try:
        from kobo.models import KoboConfig
        return KoboConfig.get()
    except Exception:
        return None
