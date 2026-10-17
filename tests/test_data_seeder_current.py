from contextlib import closing
from pathlib import Path
import uuid

import psycopg2
from psycopg2 import sql
import pytest
from werkzeug.security import check_password_hash

from scripts import data_seeder_current as seeder
from tests.test_original_branch_features import isolated_database


@pytest.fixture
def seed_database(isolated_database):
    schema = 'seeder_' + uuid.uuid4().hex
    with closing(psycopg2.connect(**isolated_database)) as conn, conn.cursor() as cursor:
        cursor.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        conn.commit()

    def connect():
        return psycopg2.connect(**isolated_database, options=f'-c search_path={schema}')

    with closing(connect()) as conn, conn.cursor() as cursor:
        cursor.execute((Path(__file__).resolve().parents[1] / 'database/capre_original_final.sql').read_text(encoding='utf-8'))
        conn.commit()
    yield connect
    with closing(psycopg2.connect(**isolated_database)) as conn, conn.cursor() as cursor:
        cursor.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
        conn.commit()


def seed(cursor, count=25):
    seeder.seed_lookups(cursor)
    seeder.seed_users(cursor)
    ids = seeder.seed_capstones(cursor, count)
    seeder.seed_capstone_people(cursor, ids)
    seeder.seed_requests(cursor, ids)


def counts(cursor):
    result = {}
    for table in ('role', 'user', 'program', 'specialization', 'capstone', 'keyword',
                  'capstone_keyword', 'author', 'capauth', 'request', 'capstone_requests',
                  'capstone_view_history', 'audit'):
        cursor.execute(sql.SQL('SELECT COUNT(*) FROM {}').format(sql.Identifier(table)))
        result[table] = cursor.fetchone()[0]
    return result


def test_current_schema_seed_is_repeatable_and_preserves_existing_users(seed_database):
    with closing(seed_database()) as conn, conn.cursor() as cursor:
        seed(cursor)
        before = counts(cursor)
        assert before['role'] == 4
        assert before['capstone'] == 25
        assert before['request'] == before['capstone_requests'] == before['capstone_view_history'] == 3
        cursor.execute('SELECT role_name FROM role ORDER BY role_id')
        assert [row[0] for row in cursor.fetchall()] == ['Student', 'Faculty', 'Admin', 'Capstone Professor']
        cursor.execute('SELECT program_code FROM program ORDER BY program_code')
        assert [row[0] for row in cursor.fetchall()] == ['BSDS', 'BSIT']
        cursor.execute('SELECT specialization_code FROM specialization ORDER BY specialization_code')
        assert [row[0] for row in cursor.fetchall()] == ['DST', 'GENERAL', 'NST', 'WST']
        cursor.execute("SELECT COUNT(*) FROM request r JOIN \"user\" u ON u.user_id = r.reviewed_by JOIN role ON role.role_id = u.role_id WHERE role_name = 'Admin'")
        assert cursor.fetchone()[0] == 2
        cursor.execute('SELECT r.password FROM ror r JOIN slug s ON s.password_id = r.password_id JOIN kappa k ON k.username_id = s.username_id WHERE k.username = %s AND s.is_current', ('mcruz',))
        assert check_password_hash(cursor.fetchone()[0], 'password123')
        cursor.execute('UPDATE "user" SET account_status = %s WHERE user_id = %s',
                       ('suspended', seeder.get_user_id_by_username(cursor, 'mcruz')))
        conn.commit()
        seed(cursor)
        assert counts(cursor) == before
        cursor.execute('SELECT account_status FROM "user" WHERE user_id = %s',
                       (seeder.get_user_id_by_username(cursor, 'mcruz'),))
        assert cursor.fetchone()[0] == 'suspended'
        conn.commit()


def test_lookup_codes_reuse_existing_labels_and_truncate_current_tables(seed_database):
    with closing(seed_database()) as conn, conn.cursor() as cursor:
        cursor.execute('INSERT INTO program (program_name) VALUES (%s) RETURNING program_id',
                       ('Bachelor of Science in Information Technology',))
        program_id = cursor.fetchone()[0]
        cursor.execute('INSERT INTO specialization (specialization_name) VALUES (%s) RETURNING specialization_id', ('DST',))
        specialization_id = cursor.fetchone()[0]
        seed(cursor, 5)
        assert seeder.get_or_create_program(cursor, 'BSIT') == program_id
        assert seeder.get_or_create_specialization(cursor, 'DST') == specialization_id
        cursor.execute('INSERT INTO auth_rate_limit VALUES (%s, CURRENT_TIMESTAMP, 1)', ('a' * 64,))
        cursor.execute('INSERT INTO signup_email_verifications (verification_id, email, code_hash, expires_at) VALUES (%s, %s, %s, CURRENT_TIMESTAMP)',
                       (str(uuid.uuid4()), 'test@example.com', 'hash'))
        seeder.truncate_tables(cursor)
        assert all(value == 0 for value in counts(cursor).values())
        for table in ('auth_rate_limit', 'signup_email_verifications'):
            cursor.execute(sql.SQL('SELECT COUNT(*) FROM {}').format(sql.Identifier(table)))
            assert cursor.fetchone()[0] == 0
        conn.commit()


def test_main_rolls_back_entire_seed_on_failure(seed_database, monkeypatch):
    monkeypatch.setattr(seeder, 'db_connect', seed_database)
    monkeypatch.setattr(seeder, 'prepare_upload_folders', lambda: None)
    monkeypatch.setattr(seeder.sys, 'argv', ['data_seeder_current.py', '--count', '5'])

    def fail(*args):
        raise RuntimeError('simulated request failure')

    monkeypatch.setattr(seeder, 'seed_requests', fail)
    with pytest.raises(RuntimeError, match='simulated request failure'):
        seeder.main()
    with closing(seed_database()) as conn, conn.cursor() as cursor:
        assert all(value == 0 for value in counts(cursor).values())
