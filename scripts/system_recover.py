"""Offline, explicitly confirmed recovery of a verified database/file bundle."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import secrets
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.db import system
from app.db.connection import db_connect
from app.services.system_maintenance import backup_root, bundle_path, verify_bundle, _postgres, _manifest_path
from app.utils.upload_cleanup import _upload_folders


def recover(bundle_id):
    if not system.maintenance_active(system.settings()):
        raise ValueError('Enable maintenance before stopping the application services.')
    manifest = verify_bundle(bundle_id)
    if not manifest.get('restore_tested_at'):
        raise ValueError('A successful restore test is required for this backup.')
    folder = bundle_path(bundle_id)
    destinations = _upload_folders()
    copies = []
    for area in manifest['areas']:
        target = Path(area['source']).resolve()
        if target not in destinations:
            raise ValueError('Backup storage mapping differs from this deployment. Resolve it before recovery.')
        prefix = f"uploads/{area['index']}/"
        for relative in manifest['sha256']:
            if relative.startswith(prefix):
                source = _manifest_path(folder, relative)
                destination = target / source.name
                if destination.is_symlink() or destination.resolve().parent != target:
                    raise ValueError('Invalid recovery destination.')
                copies.append((source, destination))
    receipt = {'backup_id': bundle_id, 'started_at': datetime.now(timezone.utc).isoformat(), 'status': 'started'}
    receipt_path = backup_root() / ('recovery-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '.json')
    receipt_path.write_text(json.dumps(receipt), encoding='utf-8')
    try:
        from flask import current_app
        _postgres(['pg_restore', '--clean', '--if-exists', '--exit-on-error', '--single-transaction', '--no-owner',
                   str(folder / 'database.dump')], current_app.config['PG_DB'])
        for source, destination in copies:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        with closing(db_connect()) as conn, conn:
            with conn.cursor() as cur:
                # A fresh generation avoids reviving cookies issued after the
                # snapshot when restoring an older session counter.
                cur.execute('UPDATE "user" SET session_version=%s', (secrets.randbits(62) + 1,))
                cur.execute("UPDATE system_setting SET maintenance_enabled=TRUE, maintenance_start=NULL, maintenance_end=NULL")
        system.record_event('production_recovery', reason='Confirmed offline recovery', details={'backup_id': bundle_id})
        receipt['status'] = 'succeeded'
    except Exception:
        receipt['status'] = 'failed; keep application services stopped'
        raise
    finally:
        receipt['finished_at'] = datetime.now(timezone.utc).isoformat()
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup-id', required=True)
    parser.add_argument('--confirm', required=True, choices=['RESTORE'])
    parser.add_argument('--services-stopped', required=True, action='store_true')
    args = parser.parse_args()
    with create_app().app_context():
        recover(args.backup_id)
    print('Recovery complete. Restart services, verify diagnostics and private files, then end maintenance.')


if __name__ == '__main__':
    main()
