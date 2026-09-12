"""Verify a PostgreSQL custom-format backup without changing a database."""

import argparse
import shutil
import subprocess
from pathlib import Path


def verify_backup(path, runner=subprocess.run):
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"Backup file does not exist: {path}")

    executable = shutil.which("pg_restore")
    if not executable:
        raise RuntimeError("pg_restore is unavailable")

    result = runner(
        [executable, "--list", "--exit-on-error", str(path)],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout or "archive could not be read").strip()
        raise RuntimeError(detail)
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    try:
        listing = verify_backup(args.input)
    except (RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    entries = len([line for line in listing.splitlines() if line.strip()])
    print(f"Backup verified: {args.input} ({entries} archive entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
