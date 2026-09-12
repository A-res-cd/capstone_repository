"""Restore a PostgreSQL custom-format backup after explicit confirmation."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import Config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm that the target database may be overwritten.",
    )
    args = parser.parse_args()

    if not args.input.is_file():
        parser.error(f"Backup file does not exist: {args.input}")
    if not args.confirm:
        parser.error("Restore is destructive. Re-run with --confirm.")

    environment = os.environ.copy()
    environment["PGPASSWORD"] = Config.PG_PASSWORD
    command = [
        "pg_restore",
        "--clean",
        "--if-exists",
        "--exit-on-error",
        "--no-owner",
        "--dbname", Config.PG_DB,
        "--host", Config.PG_HOST,
        "--port", str(Config.PG_PORT or 5432),
        "--username", Config.PG_USER,
        str(args.input),
    ]
    subprocess.run(command, check=True, env=environment)
    print(f"Database restored from: {args.input}")


if __name__ == "__main__":
    main()
