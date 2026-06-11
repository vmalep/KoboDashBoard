from django.core.cache import cache
from .models import KoboConfig


def _ttl():
    return KoboConfig.get().cache_ttl_seconds


def get_cached(key, fetch_fn):
    """Return cached value for key, or call fetch_fn() to populate it."""
    value = cache.get(key)
    if value is None:
        value = fetch_fn()
        cache.set(key, value, timeout=_ttl())
    return value


def invalidate(key):
    cache.delete(key)


def asset_list_key():
    return 'kobo_asset_list'


def schema_key(uid):
    return f'kobo_schema_{uid}'


def submissions_key(uid):
    return f'kobo_submissions_{uid}'
