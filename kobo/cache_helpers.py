from django.core.cache import cache


def get_cached(key, fetch_fn, ttl=300):
    """Return cached value for key, or call fetch_fn() to populate it."""
    value = cache.get(key)
    if value is None:
        value = fetch_fn()
        cache.set(key, value, timeout=ttl)
    return value


def get_if_cached(key):
    """Return cached value if present, else None (does not call any fetch_fn)."""
    return cache.get(key)


def invalidate(key):
    cache.delete(key)


def asset_list_key():
    return 'kobo_asset_list'


def schema_key(uid):
    return f'kobo_schema_{uid}'


def submissions_key(uid):
    return f'kobo_submissions_{uid}'
