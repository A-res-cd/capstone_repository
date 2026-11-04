"""Reproducible SQL plans against an isolated database; never production data."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Barrier
from unittest.mock import MagicMock

import psycopg2
import pytest

from app.db import archive, connection, keywords
from tests.test_original_branch_features import feature_db, isolated_database

ROOT = Path(__file__).resolve().parents[1]


def test_connection_timeout_configuration(monkeypatch):
    factory = MagicMock()
    monkeypatch.setattr(connection, 'ThreadedConnectionPool', factory)
    for name, value in {'PG_CONNECT_TIMEOUT': 7, 'PG_STATEMENT_TIMEOUT_MS': 30000,
                        'PG_LOCK_TIMEOUT_MS': 5000, 'PG_IDLE_TRANSACTION_TIMEOUT_MS': 60000}.items():
        monkeypatch.setattr(connection.Config, name, value)
    connection._create_pool()
    assert factory.call_args.kwargs['connect_timeout'] == 7
    assert factory.call_args.kwargs['options'] == (
        '-c statement_timeout=30000 -c lock_timeout=5000 -c idle_in_transaction_session_timeout=60000')


@pytest.mark.parametrize('name,value', [('PG_CONNECT_TIMEOUT', 0), ('PG_STATEMENT_TIMEOUT_MS', -1),
                                      ('PG_LOCK_TIMEOUT_MS', -1), ('PG_IDLE_TRANSACTION_TIMEOUT_MS', -1)])
def test_invalid_timeouts_are_rejected(monkeypatch, name, value):
    monkeypatch.setattr(connection.Config, name, value)
    with pytest.raises(RuntimeError, match='timeouts'):
        connection._create_pool()


def test_archive_filters_without_approval_queries(feature_db, monkeypatch):
    monkeypatch.setattr(archive, 'db_connect', feature_db)
    with closing(feature_db()) as conn, conn.cursor() as cursor:
        cursor.execute("INSERT INTO program (program_name, program_code) VALUES ('IT', 'IT') RETURNING program_id")
        program_id = cursor.fetchone()[0]
        cursor.execute("INSERT INTO specialization (specialization_name, specialization_code) VALUES ('Web', 'WEB') RETURNING specialization_id")
        specialization_id = cursor.fetchone()[0]
        cursor.execute('''INSERT INTO capstone (capstone_title, capstone_year, program_id, specialization_id)
                          SELECT 'Project ' || n, 2025 + n %% 2, %s, %s
                          FROM generate_series(1, 3) n RETURNING capstone_id''', (program_id, specialization_id))
        ids = [row[0] for row in cursor.fetchall()]
        cursor.execute('''INSERT INTO "user" (role_id, user_first_name)
                          VALUES (1, 'First'), (1, 'Second') RETURNING user_id''')
        first, second = [row[0] for row in cursor.fetchall()]
        conn.commit()
    years, programs, specializations = archive.get_archive_filters()
    assert years == archive.get_archive_years() == [2026, 2025]
    assert (program_id, 'IT') in programs
    assert (specialization_id, 'Web') in specializations


def test_keyword_batching_atomicity_and_concurrent_replacements(feature_db):
    with closing(feature_db()) as conn, conn.cursor() as cursor:
        cursor.execute((ROOT / 'migrations/20261009_normalize_capstone_keywords.sql').read_text())
        cursor.execute("INSERT INTO capstone (capstone_title) VALUES ('First'), ('Second') RETURNING capstone_id")
        ids = [row[0] for row in cursor.fetchall()]
        conn.commit()
    class CountingCursor:
        def __init__(self, cursor):
            self.cursor, self.count = cursor, 0
        def execute(self, *args):
            self.count += 1
            return self.cursor.execute(*args)
        def fetchall(self):
            return self.cursor.fetchall()
    with closing(feature_db()) as conn, conn.cursor() as cursor:
        counting = CountingCursor(cursor)
        keywords.set_capstone_keywords(counting, ids[0], ','.join(f'keyword-{n:02}' for n in range(20)))
        assert counting.count == 4  # Previously 2 + 2 * 20 = 42 round trips.
        conn.commit()
        keywords.set_capstone_keywords(cursor, ids[0], 'temporary, replacement')
        conn.rollback()
        cursor.execute('SELECT COUNT(*) FROM capstone_keyword WHERE capstone_id = %s', (ids[0],))
        assert cursor.fetchone()[0] == 20
        cursor.execute("SELECT COUNT(*) FROM keyword WHERE keyword_text = 'temporary'")
        assert cursor.fetchone()[0] == 0
    barrier = Barrier(2)
    def replace(args):
        capstone_id, value = args
        with closing(feature_db()) as conn, conn.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            barrier.wait(timeout=10)
            keywords.set_capstone_keywords(cursor, capstone_id, value)
            conn.commit()
    with ThreadPoolExecutor(max_workers=2) as workers:
        list(workers.map(replace, [(ids[0], 'alpha, beta'), (ids[1], 'beta, alpha')]))
    with ThreadPoolExecutor(max_workers=2) as workers:
        list(workers.map(replace, [(ids[0], 'alpha, gamma'), (ids[0], 'beta, delta')]))
    with closing(feature_db()) as conn, conn.cursor() as cursor:
        cursor.execute('''SELECT kw.keyword_text FROM capstone_keyword ck
                          JOIN keyword kw USING (keyword_id) WHERE ck.capstone_id = %s
                          ORDER BY kw.keyword_text''', (ids[0],))
        assert [row[0] for row in cursor.fetchall()] in (['alpha', 'gamma'], ['beta', 'delta'])
        keywords.set_capstone_keywords(cursor, ids[0], '')
        cursor.execute('SELECT COUNT(*) FROM capstone_keyword WHERE capstone_id = %s', (ids[0],))
        assert cursor.fetchone()[0] == 0


def test_pool_isolates_transactions_and_returns_connections(isolated_database, monkeypatch):
    config = connection.Config
    for name, value in {'PG_HOST': isolated_database['host'], 'PG_PORT': isolated_database['port'],
                        'PG_USER': 'postgres', 'PG_PASSWORD': '', 'PG_DB': 'postgres',
                        'PG_SSLMODE': 'disable', 'PG_POOL_MIN': 2, 'PG_POOL_MAX': 2}.items():
        monkeypatch.setattr(config, name, value)
    pool = connection._create_pool()
    monkeypatch.setattr(connection, '_pool', pool)
    barrier = Barrier(2)
    def transaction(value):
        with connection.db_connect() as conn, conn.cursor() as cursor:
            cursor.execute("SELECT set_config('application_name', %s, true), pg_backend_pid()", (value,))
            pid = cursor.fetchone()[1]
            barrier.wait(timeout=10)
            cursor.execute("SELECT current_setting('application_name')")
            assert cursor.fetchone()[0] == value
            return pid
    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            assert len(set(workers.map(transaction, ('first', 'second')))) == 2
        with pytest.raises(RuntimeError):
            with connection.db_connect() as conn, conn.cursor() as cursor:
                cursor.execute('CREATE TEMP TABLE rollback_check (id int)')
                raise RuntimeError('Abort transaction')
        with connection.db_connect() as conn, conn.cursor() as cursor:
            cursor.execute("SELECT to_regclass('pg_temp.rollback_check')")
            assert cursor.fetchone()[0] is None
        first, second = connection.db_connect(), connection.db_connect()
        try:
            with pytest.raises(psycopg2.pool.PoolError):
                connection.db_connect()
        finally:
            first.close()
            first.close()
            second.close()
        assert not pool._used
    finally:
        pool.closeall()
