import os
from unittest.mock import MagicMock
from uuid import uuid4

import psycopg2
from psycopg2 import sql
import pytest

from app.db import connection
from app.db.migration_runner import MIGRATION_TABLE_SQL, _migration_sql, migration_files
from config import Config
from scripts import setup_supabase


def test_setup_refuses_existing_tables():
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (True,)
    with pytest.raises(RuntimeError, match='already has tables'):
        setup_supabase.initialize(conn)
    conn.rollback.assert_called_once_with()
    conn.commit.assert_not_called()
    assert not any('CREATE TABLE' in call.args[0] for call in cursor.execute.call_args_list)


@pytest.mark.parametrize('storage_fails', [False, True])
def test_setup_commits_only_after_complete_setup(storage_fails):
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (False,)

    def execute(statement, *args):
        if storage_fails and 'INSERT INTO storage.buckets' in statement:
            raise RuntimeError('Storage setup failed')

    cursor.execute.side_effect = execute
    if storage_fails:
        with pytest.raises(RuntimeError, match='Storage setup failed'):
            setup_supabase.initialize(conn)
        conn.rollback.assert_called_once_with()
        conn.commit.assert_not_called()
    else:
        setup_supabase.initialize(conn)
        conn.commit.assert_called_once_with()
        conn.rollback.assert_not_called()


def test_connection_pool_uses_configured_ssl(monkeypatch):
    factory = MagicMock()
    monkeypatch.setattr(connection, 'ThreadedConnectionPool', factory)
    monkeypatch.setattr(Config, 'PG_SSLMODE', 'require')
    connection._create_pool()
    assert factory.call_args.kwargs['sslmode'] == 'require'


@pytest.mark.skipif(os.getenv('CAPRE_TEST_POSTGRES') != '1',
                    reason='Set CAPRE_TEST_POSTGRES=1 for isolated PostgreSQL checks')
def test_supabase_sql_in_isolated_postgres_transaction():
    conn = psycopg2.connect(host=Config.PG_HOST, port=Config.PG_PORT,
                            user=Config.PG_USER, password=Config.PG_PASSWORD,
                            database=Config.PG_DB, connect_timeout=5)
    suffix = uuid4().hex
    app_schema = 'test_supabase_' + suffix
    storage_schema = 'test_storage_' + suffix
    anon_role = 'test_anon_' + suffix
    auth_role = 'test_authenticated_' + suffix
    try:
        with conn.cursor() as cursor:
            for schema in (app_schema, storage_schema):
                cursor.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            for role in (anon_role, auth_role):
                cursor.execute(sql.SQL('CREATE ROLE {}').format(sql.Identifier(role)))
            cursor.execute(sql.SQL('SET LOCAL search_path TO {}').format(sql.Identifier(app_schema)))
            cursor.execute((setup_supabase.ROOT / 'database/capre_original_final.sql').read_text())
            cursor.execute(MIGRATION_TABLE_SQL)
            for migration in migration_files():
                cursor.execute(_migration_sql(migration))
            cursor.execute(sql.SQL('''CREATE TABLE {}.buckets (
                id TEXT PRIMARY KEY, name TEXT, public BOOLEAN,
                file_size_limit BIGINT, allowed_mime_types TEXT[]
            )''').format(sql.Identifier(storage_schema)))
            setup_sql = (setup_supabase.ROOT / 'database/supabase_setup.sql').read_text()
            setup_sql = setup_sql.replace('public.', app_schema + '.')
            setup_sql = setup_sql.replace('storage.buckets', storage_schema + '.buckets')
            setup_sql = setup_sql.replace('FROM anon, authenticated',
                                          f'FROM {anon_role}, {auth_role}')
            # Reapplying configuration does not duplicate lookup rows or buckets.
            cursor.execute(setup_sql)
            cursor.execute(setup_sql)
            cursor.execute(sql.SQL('SELECT COUNT(*), BOOL_AND(NOT public) FROM {}.buckets')
                           .format(sql.Identifier(storage_schema)))
            assert cursor.fetchone() == (3, True)
            cursor.execute('SELECT COUNT(*) FROM role')
            assert cursor.fetchone()[0] == 4
            cursor.execute('SELECT COUNT(*) FROM program')
            assert cursor.fetchone()[0] == 2
            cursor.execute('SELECT COUNT(*) FROM specialization')
            assert cursor.fetchone()[0] == 4
            cursor.execute('''SELECT COUNT(*), BOOL_AND(c.relrowsecurity)
                FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = %s AND c.relkind = 'r' ''', (app_schema,))
            assert cursor.fetchone() == (21, True)
            for role in (anon_role, auth_role):
                cursor.execute('SELECT has_table_privilege(%s, %s, %s)',
                               (role, app_schema + '."user"', 'SELECT'))
                assert cursor.fetchone()[0] is False
    finally:
        conn.rollback()
        conn.close()
