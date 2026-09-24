"""Real pg_dump/pg_restore against disposable databases and private temp files."""
from contextlib import closing
from importlib import import_module
from pathlib import Path
import shutil
import uuid

from flask import Flask
import psycopg2
from psycopg2 import sql
import pytest

from app.db import system
from app.services import system_maintenance as service
from tests.test_author_account_links import author_postgres

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def recovery_environment(author_postgres, monkeypatch, tmp_path):
    if not shutil.which('pg_dump') or not shutil.which('pg_restore'):
        pytest.skip('PostgreSQL client tools are required')
    source_db = 'capre_backup_test_' + uuid.uuid4().hex
    target_db = 'capre_restore_test_' + uuid.uuid4().hex
    with closing(psycopg2.connect(**author_postgres)) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            for name in (source_db, target_db):
                cur.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    def connect():
        return psycopg2.connect(**dict(author_postgres, dbname=source_db))
    with closing(connect()) as conn, conn.cursor() as cur:
        cur.execute((ROOT / 'database/capreDB.sql').read_text(encoding='utf-8').split('CREATE DATABASE capre;', 1)[1])
        cur.execute("INSERT INTO role(role_id,role_name) VALUES (1,'Student'),(2,'Faculty'),(3,'Admin'),(4,'Capstone Professor')")
        for name in ['20260924_system_administration.sql']:
            cur.execute((ROOT / 'migrations' / name).read_text(encoding='utf-8'))
        cur.execute('''INSERT INTO "user"(user_id,user_first_name,role_id,account_status)
                       VALUES(1,'Original',1,'active')''')
        conn.commit()
    app = Flask(__name__)
    app.config.update(MAINTENANCE_BACKUP_ROOT=str(tmp_path / 'backups'), PG_DB=source_db,
        PG_HOST=author_postgres['host'], PG_PORT=author_postgres['port'], PG_USER='postgres',
        PG_PASSWORD='', MAINTENANCE_RESTORE_TEST_DB=target_db)
    folders = {tmp_path / area for area in ['manuscripts', 'avatars', 'registrations']}
    for folder in folders:
        folder.mkdir()
        (folder / 'example.pdf').write_bytes(b'original private content')
    recovery = import_module('scripts.system_recover')
    for module in [service, system, recovery]:
        monkeypatch.setattr(module, 'db_connect', connect)
    monkeypatch.setattr(service, '_upload_folders', lambda: folders)
    monkeypatch.setattr(recovery, '_upload_folders', lambda: folders)
    with app.app_context():
        yield connect, folders, recovery


def test_real_backup_verification_restore_test_and_offline_recovery(recovery_environment):
    connect, folders, recovery = recovery_environment
    result = service.backup_bundle()
    assert result['verified'] and result['files'] == 4
    manifest = service.verify_bundle(result['backup_id'])
    assert len(manifest['areas']) == 3
    assert service.restore_test(result['backup_id'])['restore_tested']
    with closing(connect()) as conn, conn.cursor() as cur:
        cur.execute('UPDATE "user" SET user_first_name=\'Changed\' WHERE user_id=1')
        conn.commit()
    for folder in folders:
        (folder / 'example.pdf').write_bytes(b'changed content')
    system.save_settings(None, 'Recovery exercise', enabled=True, start=None, end=None, notice='Recovery')
    recovery.recover(result['backup_id'])
    with closing(connect()) as conn, conn.cursor() as cur:
        cur.execute('SELECT user_first_name,session_version FROM "user" WHERE user_id=1')
        name, epoch = cur.fetchone()
    assert name == 'Original' and epoch > 0
    assert system.maintenance_active(system.settings())
    assert all((folder / 'example.pdf').read_bytes() == b'original private content' for folder in folders)
    assert list(service.backup_root().glob('recovery-*.json'))


def test_tampered_bundle_cannot_be_restored(recovery_environment):
    _, _, _ = recovery_environment
    result = service.backup_bundle()
    (service.bundle_path(result['backup_id']) / 'database.dump').write_bytes(b'corrupted')
    with pytest.raises(ValueError, match='integrity'):
        service.restore_test(result['backup_id'])
