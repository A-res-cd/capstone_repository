"""Bounded maintenance operations; no shell commands supplied by the browser."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid
from urllib.parse import urlsplit

from flask import current_app
from psycopg2 import sql

from app.db import system
from app.db.connection import db_connect
from app.db.migration_runner import migration_status
from app.db.health import database_is_ready
from app.utils.upload_cleanup import (
    _upload_folders, _referenced_upload_names, _retention_days, _orphaned_uploads,
)


def backup_root():
    configured = Path(current_app.config['MAINTENANCE_BACKUP_ROOT']).absolute()
    if current_app.static_folder:
        public = Path(current_app.static_folder).absolute()
        if configured.is_relative_to(public) or configured.resolve().is_relative_to(public.resolve()):
            raise ValueError('Backups must be stored outside the public static directory.')
    return configured.resolve()


def checksum(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def storage_inventory():
    referenced = _referenced_upload_names()
    retention = _retention_days()
    if referenced is None or retention is None:
        raise ValueError('Could not verify database references or retention settings. Cleanup is unavailable.')
    folders = sorted(_upload_folders(), key=str)
    found = set()
    result = []
    for index, folder in enumerate(folders):
        if not folder.is_dir():
            result.append({'area': index + 1, 'status': 'unavailable', 'files': 0, 'bytes': 0, 'free_bytes': None})
            continue
        files = [path for path in folder.iterdir() if path.is_file() and not path.is_symlink()]
        found.update(path.name for path in files)
        result.append({'area': index + 1, 'status': 'healthy', 'files': len(files),
                       'bytes': sum(path.stat().st_size for path in files), 'free_bytes': shutil.disk_usage(folder).free})
    candidates = _orphaned_uploads(referenced, retention)
    return {'areas': result, 'missing_references': len(referenced - found), 'retention_days': retention,
            'candidates': candidates}


def cleanup_preview():
    inventory = storage_inventory()
    entries = inventory['candidates']
    digest = hashlib.sha256(json.dumps([
        [e['path'], e['size_bytes'], e['modified_at_ns']] for e in sorted(entries, key=lambda x: x['path'])
    ], separators=(',', ':')).encode()).hexdigest()
    return inventory, digest


def cleanup_confirmed(expected_digest):
    inventory, digest = cleanup_preview()
    if digest != expected_digest:
        raise ValueError('Cleanup inventory changed. Create a fresh preview.')
    if not system.maintenance_active(system.settings()):
        raise ValueError('Enable maintenance mode before cleanup.')
    deleted = 0
    folders = _upload_folders()
    for entry in inventory['candidates']:
        path = Path(entry['path'])
        if path.is_symlink() or not path.is_file() or path.resolve().parent not in folders:
            raise ValueError('Cleanup file no longer matches its approved location.')
        # Recheck DB references immediately before each deletion.
        references = _referenced_upload_names()
        if references is None:
            raise ValueError('Reference check failed; cleanup stopped.')
        stat = path.stat()
        if path.name in references or stat.st_size != entry['size_bytes'] or stat.st_mtime_ns != entry['modified_at_ns']:
            raise ValueError('File changed; cleanup stopped. Create a fresh preview.')
        path.unlink()
        deleted += 1
    return {'deleted_files': deleted}


def diagnostics():
    checks = []
    def check(name, fn, healthy_message):
        try:
            ok = fn()
            checks.append({'name': name, 'status': 'healthy' if ok else 'unavailable',
                           'detail': healthy_message if ok else 'Check configuration or service availability.'})
        except Exception:
            checks.append({'name': name, 'status': 'unavailable', 'detail': 'Check the service and deployment configuration.'})
    check('Database and migrations', database_is_ready, 'Database reachable and migrations match.')
    check('Private storage', lambda: all(p.is_dir() and os.access(p, os.R_OK | os.W_OK) for p in _upload_folders()),
          'Private storage directories are readable and writable.')
    check('Backup tools', lambda: shutil.which('pg_dump') and shutil.which('pg_restore'), 'PostgreSQL backup tools found.')
    check('OCR', lambda: shutil.which('tesseract'), 'Tesseract executable found.')
    checks.append({'name': 'Email delivery', 'status': 'not checked',
                   'detail': 'SMTP configuration present; delivery not tested.' if current_app.config.get('MAIL_SERVER')
                   else 'SMTP server is not configured.'})
    checks.append({'name': 'Public HTTPS', 'status': 'not checked',
                   'detail': 'Verify externally through the deployed HTTPS address.'})
    return {'checked_at': datetime.now(timezone.utc).isoformat(), 'checks': checks}


def _postgres(command, database=None, timeout=1800):
    config = current_app.config
    executable = shutil.which(command[0])
    if not executable:
        raise ValueError(f'{command[0]} is not installed.')
    environment = os.environ.copy()
    environment['PGPASSWORD'] = config['PG_PASSWORD']
    args = [executable] + command[1:] + [
        '--host', config['PG_HOST'], '--port', str(config.get('PG_PORT') or 5432),
        '--username', config['PG_USER'],
    ]
    if database:
        args += ['--dbname', database]
    result = subprocess.run(args, env=environment, capture_output=True, timeout=timeout,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        # Tool stderr can contain connection details and object contents.
        raise ValueError(f'{command[0]} failed. Inspect the protected server logs and database service.')
    return result


def bundle_path(bundle_id):
    if not isinstance(bundle_id, str) or len(bundle_id) != 32 or any(c not in '0123456789abcdef' for c in bundle_id):
        raise ValueError('Invalid backup identifier.')
    path = backup_root() / bundle_id
    if path.is_symlink() or path.resolve().parent != backup_root():
        raise ValueError('Invalid backup location.')
    return path


def _manifest_path(folder, relative):
    path = folder / relative
    if path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()) or not path.is_file():
        raise ValueError('Backup contains an invalid file reference.')
    return path


def verify_bundle(bundle_id):
    folder = bundle_path(bundle_id)
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('id') != bundle_id or 'database.dump' not in manifest.get('sha256', {}):
        raise ValueError('Backup manifest is invalid.')
    for relative, expected in manifest['sha256'].items():
        if checksum(_manifest_path(folder, relative)) != expected:
            raise ValueError('Backup integrity check failed.')
    executable = shutil.which('pg_restore')
    if not executable:
        raise ValueError('pg_restore is not installed.')
    result = subprocess.run([executable, '--list', str(folder / 'database.dump')], capture_output=True, timeout=60,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise ValueError('Database archive could not be verified.')
    manifest['verified_at'] = datetime.now(timezone.utc).isoformat()
    _save_manifest(folder, manifest)
    return manifest


def _save_manifest(folder, manifest):
    temporary = folder / 'manifest.tmp'
    temporary.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    temporary.replace(folder / 'manifest.json')


def backup_bundle():
    root = backup_root()
    if any(root.is_relative_to(folder) or folder.is_relative_to(root) for folder in _upload_folders()):
        raise ValueError('Backup storage must be separate from private uploads.')
    root.mkdir(parents=True, exist_ok=True)
    bundle_id = uuid.uuid4().hex
    folder = bundle_path(bundle_id)
    folder.mkdir()
    manifest = {'id': bundle_id, 'created_at': datetime.now(timezone.utc).isoformat(), 'sha256': {}, 'areas': []}
    # Hold SHARE locks while taking the database and file snapshot. DB readers
    # continue; writes wait. Lock timeout avoids hanging behind long transactions.
    with closing(db_connect()) as conn, conn:
        with conn.cursor() as cur:
            cur.execute("SET lock_timeout='10s'")
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname=current_schema() AND tablename NOT IN ('maintenance_job','system_event','system_setting') ORDER BY tablename")
            tables = [sql.Identifier(row[0]) for row in cur.fetchall()]
            if tables:
                cur.execute(sql.SQL('LOCK TABLE {} IN SHARE MODE').format(sql.SQL(',').join(tables)))
            _postgres(['pg_dump', '--format=custom', '--no-owner', '--file', str(folder / 'database.dump')], current_app.config['PG_DB'])
            for index, source in enumerate(sorted(_upload_folders(), key=str)):
                if not source.is_dir():
                    raise ValueError('A private storage directory is missing; backup is incomplete.')
                destination = folder / 'uploads' / str(index)
                destination.mkdir(parents=True)
                manifest['areas'].append({'index': index, 'source': str(source)})
                for path in source.iterdir():
                    if path.is_file() and not path.is_symlink():
                        shutil.copy2(path, destination / path.name)
            for path in folder.rglob('*'):
                if path.is_file():
                    manifest['sha256'][path.relative_to(folder).as_posix()] = checksum(path)
    _save_manifest(folder, manifest)
    verify_bundle(bundle_id)
    prune_backups(system.settings()['backup_keep'])
    return {'backup_id': bundle_id, 'files': len(manifest['sha256']), 'verified': True}


def list_backups():
    root = backup_root()
    if not root.is_dir():
        return []
    rows = []
    for path in root.iterdir():
        if path.is_symlink() or not path.is_dir():
            continue
        try:
            manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
            rows.append({key: manifest.get(key) for key in ('id', 'created_at', 'verified_at', 'restore_tested_at')})
        except (OSError, ValueError):
            rows.append({'id': path.name, 'created_at': None, 'verified_at': None, 'restore_tested_at': None})
    return sorted(rows, key=lambda row: row['created_at'] or '', reverse=True)


def prune_backups(keep):
    verified = [row for row in list_backups() if row['verified_at']]
    # Preserve the newest restore-tested bundle even when outside retention.
    tested = next((row['id'] for row in verified if row['restore_tested_at']), None)
    for row in verified[keep:]:
        if row['id'] != tested:
            folder = bundle_path(row['id'])
            if folder.is_dir() and folder.resolve().parent == backup_root():
                shutil.rmtree(folder)
                system.record_event('backup_retained_count', details={'removed_backup_id': row['id']})


def restore_test(bundle_id):
    target = current_app.config.get('MAINTENANCE_RESTORE_TEST_DB')
    if not target or target == current_app.config['PG_DB'] or not target.startswith('capre_restore_test_'):
        raise ValueError('Provision a dedicated capre_restore_test_* database before running a restore test.')
    manifest = verify_bundle(bundle_id)
    _postgres(['pg_restore', '--clean', '--if-exists', '--exit-on-error', '--single-transaction', '--no-owner',
               str(bundle_path(bundle_id) / 'database.dump')], target)
    # A successful pg_restore restores all archive entries, including constraints.
    manifest['restore_tested_at'] = datetime.now(timezone.utc).isoformat()
    _save_manifest(bundle_path(bundle_id), manifest)
    return {'backup_id': bundle_id, 'restore_tested': True}


def run_job(row):
    kind, payload = row['kind'], row['payload']
    if kind == 'diagnostics':
        return diagnostics()
    if kind == 'backup':
        return backup_bundle()
    if kind == 'verify_backup':
        manifest = verify_bundle(payload['backup_id'])
        return {'backup_id': manifest['id'], 'verified': True}
    if kind == 'restore_test':
        return restore_test(payload['backup_id'])
    if kind == 'cleanup':
        return cleanup_confirmed(payload['digest'])
    if kind == 'archive_purge':
        from app.db.archive import purge_expired_archived_capstones
        return {'deleted_records': purge_expired_archived_capstones(raise_errors=True)}
    if kind == 'recovery_email':
        from app import mail
        from app.utils.account_emails import _message
        base = current_app.config.get('PUBLIC_BASE_URL') or ''
        parsed = urlsplit(base)
        if parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Configure the public HTTPS address before sending recovery instructions.')
        recipient = system.recovery_recipient(payload['user_id'])
        if not recipient:
            raise ValueError('No eligible primary email contact was found.')
        mail.send(_message('CAPRE account recovery instructions', recipient['email'],
            name=recipient['username'], category='Account security', title='Recover your account',
            preview='Your system administrator has requested account recovery.',
            introduction='Your system administrator has asked you to review your CAPRE account security.',
            instruction='Start the verified-email password recovery flow at ' + base.rstrip('/') + '/forgot_password',
            note='Your password has not been changed. If your account is suspended, contact support after resetting it.',
            security='Do not share your password or one-time codes with anyone.'))
        return {'user_id': payload['user_id'], 'instructions_sent': True}
    raise ValueError('Unknown job type.')
