from django import template

register = template.Library()


@register.filter
def dict_get(d, key):
    """Return d[key] — allows variable-key dict lookup in templates."""
    if isinstance(d, dict):
        return d.get(key)
    return None
