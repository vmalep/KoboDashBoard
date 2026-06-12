REGISTRY = {}


def register(uid):
    """Decorator: @register('form-uid') on a FormModule subclass."""
    def decorator(cls):
        REGISTRY[uid] = cls()
        return cls
    return decorator


def get_module(uid):
    """Return the registered FormModule instance for uid, or None."""
    return REGISTRY.get(uid)


from form_modules import dnh  # noqa: E402, F401 — triggers @register
