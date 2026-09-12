"""Create a PostgreSQL custom-format backup without exposing the password."""

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import Config


def default_output():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path("backups") / f"capre_{stamp}.dump"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=default_output())
    args = parser.parse_args()

    if args.output.exists():
        parser.error(f"Backup already exists: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    environment = os.environ.copy()
    environment["PGPASSWORD"] = Config.PG_PASSWORD
    command = [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--file", str(args.output),
        "--host", Config.PG_HOST,
        "--port", str(Config.PG_PORT or 5432),
        "--username", Config.PG_USER,
        Config.PG_DB,
    ]
    subprocess.run(command, check=True, env=environment)
    print(f"Backup created: {args.output}")


if __name__ == "__main__":
    main()
