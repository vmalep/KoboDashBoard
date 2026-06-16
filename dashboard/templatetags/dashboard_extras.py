from django import template

register = template.Library()


@register.filter
def dict_get(d, key):
    """Return d[key] — allows variable-key dict lookup in templates."""
    if isinstance(d, dict):
        return d.get(key)
    return None


@register.filter
def pie_field_choices(pie_choices, widget):
    """Return the choice list for widget's current field from pie_choices.

    Used in the editor form: the filter argument is the whole widget dict
    (a simple variable, not a dotted path) so Django 6's strict filter-arg
    resolution never raises VariableDoesNotExist.
    """
    if not isinstance(pie_choices, dict) or not isinstance(widget, dict):
        return None
    field = widget.get('field', '')
    return pie_choices.get(field) or None
