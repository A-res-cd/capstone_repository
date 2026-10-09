import os
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import psycopg2
from psycopg2 import sql
import pytest

from app.db import archive, capstones
from app.db.keywords import split_keywords
from app.db.migration_runner import _migration_sql, migration_files
from config import Config


@pytest.mark.parametrize('value, expected', [
    (None, []), (' , , ', []),
    (' AI, web, AI, ai, Machine Learning ', ['ai', 'machine learning', 'web']),
])
def test_split_keywords(value, expected):
    assert split_keywords(value) == expected


def test_keyword_failure_rolls_back_capstone_update(monkeypatch):
    conn = MagicMock()
    monkeypatch.setattr(capstones, 'db_connect', lambda: conn)

    def fail(*args):
        raise RuntimeError('Keyword insert failed')

    monkeypatch.setattr(capstones, 'set_capstone_keywords', fail)
    ok, _ = capstones.update_capstone_record(
        1, None, 1, 1, 'Title', 2026, 'test.pdf', '1st', capstone_keywords='ai',
    )
    assert not ok
    conn.commit.assert_not_called()
    conn.rollback.assert_called_once_with()


@pytest.mark.skipif(os.getenv('CAPRE_TEST_POSTGRES') != '1',
                    reason='Set CAPRE_TEST_POSTGRES=1 for isolated PostgreSQL checks')
@pytest.mark.parametrize('legacy', [True, False])
def test_keyword_schema_and_workflows(monkeypatch, legacy):
    root = Path(__file__).resolve().parents[1]
    conn = psycopg2.connect(host=Config.PG_HOST, port=Config.PG_PORT,
                            user=Config.PG_USER, password=Config.PG_PASSWORD,
                            database=Config.PG_DB, connect_timeout=5)

    class TransactionConnection:
        # All app operations stay inside this test's rolled-back schema transaction.
        def cursor(self, *args, **kwargs):
            return conn.cursor(*args, **kwargs)

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    try:
        with conn.cursor() as cursor:
            schema = 'test_keywords_' + uuid4().hex
            cursor.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            cursor.execute(sql.SQL('SET LOCAL search_path TO {}').format(sql.Identifier(schema)))
            source = 'capreDB.sql' if legacy else 'capre_original_final.sql'
            cursor.execute((root / 'database' / source).read_text(encoding='utf-8'))
            if legacy:
                cursor.execute("INSERT INTO keyword (capstone_keywords) VALUES (' AI, web, AI, ai, ') RETURNING keyword_id")
                old_id = cursor.fetchone()[0]
                cursor.execute("INSERT INTO capstone (keyword_id, capstone_title) VALUES (%s, 'Legacy A'), (%s, 'Legacy B'), (NULL, 'Empty')",
                               (old_id, old_id))
                for migration in migration_files():
                    cursor.execute(_migration_sql(migration))
                cursor.execute('SELECT keyword_text FROM keyword ORDER BY keyword_text')
                assert cursor.fetchall() == [('ai',), ('web',)]
                cursor.execute('SELECT COUNT(*) FROM capstone_keyword')
                assert cursor.fetchone()[0] == 4
            # Safe on a fresh final schema and on an already normalized schema.
            cursor.execute(_migration_sql(root / 'migrations/20261009_normalize_capstone_keywords.sql'))
            cursor.execute("INSERT INTO program (program_name) VALUES ('Test') RETURNING program_id")
            program_id = cursor.fetchone()[0]
            cursor.execute("INSERT INTO specialization (specialization_name) VALUES ('Test') RETURNING specialization_id")
            specialization_id = cursor.fetchone()[0]

        transaction = TransactionConnection()
        monkeypatch.setattr(capstones, 'db_connect', lambda: transaction)
        monkeypatch.setattr(archive, 'db_connect', lambda: transaction)
        monkeypatch.setattr(archive, 'purge_expired_archived_capstones', lambda: 0)
        ids = []
        for title, keywords in [('First', 'AI, web, ai'), ('Second', 'AI'), ('No keywords', '')]:
            ok, capstone_id = capstones.create_capstone_project(
                None, specialization_id, program_id, title, 2026, 'test.pdf', '1st',
                capstone_keywords=keywords,
            )
            assert ok, capstone_id
            ids.append(capstone_id)

        assert capstones.get_capstone_details(ids[0])['capstone_keywords'] == 'ai, web'
        assert capstones.get_capstone_details(ids[2])['capstone_keywords'] is None
        rows, total = capstones.get_all_capstones(program_id=program_id)
        assert total == len(rows) == 3
        rows, total = archive.get_archive_capstones(search='ai', search_scope='keyword', program=program_id)
        assert total == len(rows) == 2
        assert capstones.update_capstone_record(
            ids[0], None, specialization_id, program_id, 'First', 2026, 'test.pdf', '1st',
            capstone_keywords='Database, database',
        )[0]
        assert capstones.get_capstone_details(ids[0])['capstone_keywords'] == 'database'
        assert capstones.get_capstone_details(ids[1])['capstone_keywords'] == 'ai'
        corpus = {row['capstone_id']: row for row in capstones.get_capstones_corpus()}
        assert corpus[ids[0]]['capstone_keywords'] == 'database'
        assert capstones.update_keyword(ids[0], '')[0]
        assert capstones.get_capstone_details(ids[0])['capstone_keywords'] is None
        with conn.cursor() as cursor:
            cursor.execute('UPDATE capstone SET is_archived = TRUE WHERE capstone_id = %s', (ids[1],))
        rows, total = archive.get_archived_capstones(program_id=program_id)
        assert total == len(rows) == 1
        assert archive.delete_capstone(ids[1])[0]
        with conn.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM capstone_keyword WHERE capstone_id = %s', (ids[1],))
            assert cursor.fetchone()[0] == 0
            cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = 'capstone'",
                           (schema,))
            assert 'keyword_id' not in {row[0] for row in cursor.fetchall()}
            cursor.execute("SELECT keyword_id FROM keyword WHERE keyword_text = 'ai'")
            keyword_id = cursor.fetchone()[0]
            cursor.execute('INSERT INTO capstone_keyword VALUES (%s, %s)', (ids[0], keyword_id))
            invalid_statements = [
                ("INSERT INTO keyword (keyword_text) VALUES (%s)", ('ai',)),
                ("INSERT INTO keyword (keyword_text) VALUES (%s)", ('ai, web',)),
                ("INSERT INTO keyword (keyword_text) VALUES (%s)", ('',)),
                ("INSERT INTO keyword (keyword_text) VALUES (%s)", (' AI ',)),
                ("INSERT INTO capstone_keyword VALUES (%s, %s)", (ids[0], keyword_id)),
            ]
            for statement, params in invalid_statements:
                cursor.execute('SAVEPOINT keyword_constraint_check')
                with pytest.raises(psycopg2.IntegrityError):
                    cursor.execute(statement, params)
                cursor.execute('ROLLBACK TO SAVEPOINT keyword_constraint_check')
    finally:
        conn.rollback()
        conn.close()
