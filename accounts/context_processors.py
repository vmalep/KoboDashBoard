from django.conf import settings
from django.contrib.auth import get_user_model
from kobodashboard import __version__ as APP_VERSION

_LANG_NAMES = [
    ('fr', 'Français'),
    ('en', 'English'),
    ('es', 'Español'),
    ('ar', 'العربية'),
    ('ru', 'Русский'),
]
_LANG_NAME_MAP = dict(_LANG_NAMES)


def _check_power_user(user):
    if not user.is_authenticated:
        return False
    if user.email in settings.POWER_USER_EMAILS:
        return True
    try:
        return user.profile.is_power_user
    except Exception:
        return False


def pending_users(request):
    if _check_power_user(request.user):
        count = get_user_model().objects.filter(is_active=False).count()
        return {'pending_users_count': count}
    return {'pending_users_count': 0}


def user_roles(request):
    from django.utils.translation import get_language
    lang = (get_language() or 'fr')[:2]
    lang_ctx = {
        'current_lang': lang,
        'current_lang_name': _LANG_NAME_MAP.get(lang, lang),
        'all_languages': _LANG_NAMES,
        'site_config': _site_config(),
    }
    if not request.user.is_authenticated:
        return {'is_power_user': False, 'is_group_admin': False, 'app_version': APP_VERSION, **lang_ctx}
    from kobo.models import DashboardGroup
    is_power = _check_power_user(request.user)
    is_gadmin = not is_power and DashboardGroup.objects.filter(admins=request.user).exists()
    return {'is_power_user': is_power, 'is_group_admin': is_gadmin, 'app_version': APP_VERSION, **lang_ctx}


def _site_config():
    try:
        from kobo.models import KoboConfig
        return KoboConfig.get()
    except Exception:
        return None
