"""
Settings of the app. Each one is read, in this order, from:

1. the project's settings.py (e.g. ``HISOBOT_LOGIN_REQUIRED = True``),
2. environment variables - including a ``.env`` file next to manage.py
   (loaded with python-dotenv when it is installed),
3. the defaults below.

Only HEMIS_API_URL and HEMIS_API_TOKEN have no default: they belong to your
university and must never be committed - put them in .env (see .env.example).
"""

from __future__ import annotations

import os
from pathlib import Path

from django.conf import settings

_env_loaded = False


def _base_dir() -> Path:
    return Path(getattr(settings, "BASE_DIR", Path.cwd()))


def _load_env() -> None:
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True
    try:
        from dotenv import load_dotenv
    except ImportError:  # python-dotenv is optional: real environment variables work too
        return
    load_dotenv(_base_dir() / ".env", override=False)


def get(name: str, default=None):
    if hasattr(settings, name):
        return getattr(settings, name)
    _load_env()
    value = os.environ.get(name)
    return default if value in (None, "") else value


def get_bool(name: str, default: bool = False) -> bool:
    value = get(name, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def get_int(name: str, default: int) -> int:
    try:
        return int(get(name, default))
    except (TypeError, ValueError):
        return default


def api_url() -> str:
    url = get("HEMIS_API_URL", "")
    return url if not url or url.endswith("/") else url + "/"


def api_token() -> str:
    return get("HEMIS_API_TOKEN", "")


def data_file() -> Path:
    """Where the downloaded report is kept (JSON)."""
    return Path(get("HISOBOT_DATA_FILE", _base_dir() / "hisobot_data.json"))


def login_required() -> bool:
    return get_bool("HISOBOT_LOGIN_REQUIRED", False)


def api_key() -> str:
    """Lets programs read /data.json without logging in when
    HISOBOT_LOGIN_REQUIRED is on (header X-Hisobot-Key, or ?key=)."""
    return get("HISOBOT_API_KEY", "")


def auto_refresh_hours() -> int:
    """Older data than this is refreshed in the background when the page is
    opened (0 = only by the button / the management command)."""
    return get_int("HISOBOT_AUTO_REFRESH_HOURS", 0)


def workers() -> int:
    return max(1, get_int("HISOBOT_WORKERS", 3))


def utc_offset_hours() -> int:
    return get_int("HISOBOT_UTC_OFFSET", 5)  # Tashkent
