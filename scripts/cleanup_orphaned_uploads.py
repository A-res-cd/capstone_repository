"""Delete old unreferenced private uploads after explicit confirmation."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from app.utils.upload_cleanup import delete_orphaned_uploads


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm deletion of unchanged, unreferenced files past retention.",
    )
    args = parser.parse_args()
    if not args.confirm:
        parser.error("Deletion is destructive. Re-run with --confirm.")

    app = create_app()
    with app.app_context():
        deleted = delete_orphaned_uploads()
    print(f"Deleted {deleted} orphaned upload(s).")


if __name__ == "__main__":
    main()
