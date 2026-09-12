"""Report old unreferenced private uploads without deleting anything."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from app.utils.upload_cleanup import find_orphaned_uploads


def main():
    app = create_app()
    with app.app_context():
        orphaned = find_orphaned_uploads()
    for entry in orphaned:
        entry["modified_at"] = entry["modified_at"].isoformat()
    print(json.dumps(orphaned, indent=2))


if __name__ == "__main__":
    main()
