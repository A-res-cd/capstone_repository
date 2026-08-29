import os
from dotenv import load_dotenv

load_dotenv()

# Vars the app cannot safely run without. A missing SECRET_KEY would let
# Flask fall back to an insecure default (or crash later with a confusing
# error on the first session write); better to fail loudly at boot.
_REQUIRED_ENV_VARS = ("SECRET_KEY", "PG_HOST", "PG_USER", "PG_PASSWORD", "PG_DB")


def _require_env(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            "Set it in your .env file or environment before starting the app."
        )
    return value


def _int_env(name, default=None):
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError(f"Environment variable {name}={raw!r} must be an integer.")


for _var in _REQUIRED_ENV_VARS:
    _require_env(_var)


class Config:
    SECRET_KEY = os.environ["SECRET_KEY"]

    PG_HOST = os.environ["PG_HOST"]
    PG_PORT = _int_env("PG_PORT")
    PG_USER = os.environ["PG_USER"]
    PG_PASSWORD = os.environ["PG_PASSWORD"]
    PG_DB = os.environ["PG_DB"]
    PG_POOL_MIN = _int_env("PG_POOL_MIN")
    PG_POOL_MAX = _int_env("PG_POOL_MAX")

    MAIL_SERVER = os.environ.get("MAIL_SERVER")
    # Optional in dev (mail may be unconfigured locally) but must not crash
    # the whole app with a bare TypeError if unset — default to the
    # standard TLS submission port instead.
    MAIL_PORT = _int_env("MAIL_PORT", 587)
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_USERNAME")

    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER")

    MAX_CONTENT_LENGTH = 25 * 1024 * 1024  # 25 MB cap on request/upload size

    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
