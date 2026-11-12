"""Read secrets from the environment, loading the repository's .env once.

Values are never logged or written anywhere.
"""
import os

from friday.core.paths import HOME

_loaded = False


def _load_env_files():
    global _loaded
    if _loaded:
        return
    _loaded = True
    # engine/.env first, then the repository root's.
    for path in (HOME / ".env", HOME.parent / ".env"):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def secret(name):
    """Return the secret's value, or '' if it isn't set."""
    _load_env_files()
    return os.environ.get(name, "")
