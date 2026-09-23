"""Apply or inspect CAPRE database migrations without starting the web app."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import argparse

from app.db.migration_runner import MigrationError, migration_status, upgrade_database


def main(argv=None):
    parser = argparse.ArgumentParser(description="Manage CAPRE PostgreSQL migrations.")
    parser.add_argument("command", choices=("status", "upgrade"))
    args = parser.parse_args(argv)

    try:
        if args.command == "status":
            state = migration_status()
            print(f"Applied: {len(state['applied'])}")
            print(f"Pending: {len(state['pending'])}")
            for name in state["pending"]:
                print(f"  pending: {name}")
            return 0

        applied = upgrade_database()
        if applied:
            print("Applied:")
            for name in applied:
                print(f"  {name}")
        else:
            print("Database is already up to date.")
        return 0
    except Exception as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())