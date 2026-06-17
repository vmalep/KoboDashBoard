import importlib
import inspect
import logging
from pathlib import Path

REGISTRY = {}

_log = logging.getLogger(__name__)


def register(uid):
    """Decorator: @register('form-uid') on a FormModule subclass."""
    def decorator(cls):
        obj = cls()
        obj._uid = uid
        obj._source_file = inspect.getfile(cls)
        REGISTRY[uid] = obj
        return cls
    return decorator


def get_module(uid):
    """Return the registered FormModule instance for uid, or None."""
    return REGISTRY.get(uid)


# Auto-discover all .py files in this directory (except __init__ and base)
_dir = Path(__file__).parent
for _path in sorted(_dir.glob('*.py')):
    if _path.stem not in ('__init__', 'base'):
        try:
            importlib.import_module(f'form_modules.{_path.stem}')
        except Exception as exc:
            _log.error('Failed to load form module %s: %s', _path.stem, exc)
