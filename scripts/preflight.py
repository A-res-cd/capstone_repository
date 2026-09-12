"""Validate production configuration before starting CAPRE."""

import os
import shlex
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import Config
from app.db.health import database_is_ready


def _truthy(value):
    return str(value or "").lower() in {"1", "true", "yes", "on"}


def _scanner_available(command):
    if not command:
        return False
    command = str(command).strip()
    direct_path = Path(command)
    if direct_path.is_file():
        return True
    try:
        executable = shlex.split(command, posix=os.name != "nt")[0]
    except (IndexError, ValueError):
        return False
    return bool(shutil.which(executable))


def _command_available(command):
    return bool(shutil.which(command))


def configuration_failures(config=Config, environ=None):
    if environ is None:
        environ = os.environ
    failures = []
    if _truthy(environ.get("FLASK_DEBUG")):
        failures.append("FLASK_DEBUG must be disabled")
    if not getattr(config, "UPLOAD_ANTIVIRUS_REQUIRED", False):
        failures.append("UPLOAD_ANTIVIRUS_REQUIRED must be true")
    elif not _scanner_available(getattr(config, "UPLOAD_ANTIVIRUS_COMMAND", None)):
        failures.append("UPLOAD_ANTIVIRUS_COMMAND is unavailable")
    if not getattr(config, "UPLOAD_RETENTION_CLEANUP_ENABLED", False):
        failures.append("UPLOAD_RETENTION_CLEANUP_ENABLED must be true")
    if getattr(config, "UPLOAD_ORPHAN_RETENTION_DAYS", 0) < 1:
        failures.append("UPLOAD_ORPHAN_RETENTION_DAYS must be positive")
    if getattr(config, "UPLOAD_ANTIVIRUS_TIMEOUT_SECONDS", 0) < 1:
        failures.append("UPLOAD_ANTIVIRUS_TIMEOUT_SECONDS must be positive")
    if getattr(config, "SESSION_COOKIE_SECURE", False) is not True:
        failures.append("SESSION_COOKIE_SECURE must be true")
    if getattr(config, "SESSION_COOKIE_HTTPONLY", False) is not True:
        failures.append("SESSION_COOKIE_HTTPONLY must be true")
    if getattr(config, "MAX_CONTENT_LENGTH", 0) <= 0:
        failures.append("MAX_CONTENT_LENGTH must be positive")
    for command in ("pg_dump", "pg_restore"):
        if not _command_available(command):
            failures.append(f"{command} is unavailable")
    return failures


def main():
    failures = configuration_failures()
    if not failures and not database_is_ready():
        failures.append("database is not ready or migrations are incomplete")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1

    print("PASS: CAPRE production preflight")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
