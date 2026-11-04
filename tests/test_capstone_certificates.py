"""Certificate migration preserves capstones and enforces certificate ownership."""
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import psycopg2
from psycopg2 import sql
import pytest

from app.db import migration_runner, capstones
from tests.test_original_branch_features import isolated_database


def test_capstone_certificates_migration(isolated_database, monkeypatch, tmp_path):
    schema = 'certificates_' + uuid4().hex
    with closing(psycopg2.connect(**isolated_database)) as conn, conn.cursor() as cursor:
        cursor.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        cursor.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
        cursor.execute('CREATE TABLE capstone (capstone_id SERIAL PRIMARY KEY, capstone_title TEXT)')
        cursor.execute("INSERT INTO capstone(capstone_title) VALUES ('Existing project'), ('Second project')")
        conn.commit()

        def connect():
            return psycopg2.connect(**isolated_database, options=f'-c search_path={schema}')

        monkeypatch.setattr(migration_runner, 'db_connect', connect)
        name = '20261107_capstone_certificates.sql'
        source = Path(__file__).resolve().parents[1] / 'migrations' / name
        (tmp_path / name).write_bytes(source.read_bytes())
        try:
            assert migration_runner.upgrade_database(tmp_path) == [name]
            assert migration_runner.upgrade_database(tmp_path) == []
            cursor.execute('SELECT capstone_title,copyright_cert_id,utilization_cert_id FROM capstone ORDER BY capstone_id')
            assert cursor.fetchall() == [('Existing project', None, None), ('Second project', None, None)]
            details = {
                'copyright': {'number': 'COPY-2', 'date': '2026-11-05', 'file': 'copyright-2.pdf'},
                'utilization': {'date': '2026-11-05', 'file': 'utilization-2.pdf'},
            }
            capstones._set_capstone_certificates(cursor, 2, details)
            cursor.execute('SELECT copyright_cert_id,utilization_cert_id FROM capstone WHERE capstone_id=2')
            original_ids = cursor.fetchone()
            details['copyright']['number'] = 'COPY-UPDATED'
            capstones._set_capstone_certificates(cursor, 2, details)
            cursor.execute('SELECT copyright_cert_id,utilization_cert_id FROM capstone WHERE capstone_id=2')
            assert cursor.fetchone() == original_ids
            cursor.execute('SELECT copyright_cert_num FROM copyright WHERE copyright_cert_id=%s', (original_ids[0],))
            assert cursor.fetchone()[0] == 'COPY-UPDATED'
            # A later failure rolls back links and certificate rows together.
            conn.rollback()
            cursor.execute('SELECT copyright_cert_id,utilization_cert_id FROM capstone WHERE capstone_id=2')
            assert cursor.fetchone() == (None, None)
            cursor.execute('SELECT COUNT(*) FROM copyright')
            assert cursor.fetchone()[0] == 0
            cursor.execute("INSERT INTO copyright(copyright_cert_num,copyright_cert_date,copyright_cert_file) VALUES ('CERT-1','2026-11-05','copyright.pdf') RETURNING copyright_cert_id")
            copyright_id = cursor.fetchone()[0]
            cursor.execute("INSERT INTO utilization(utilization_file,utilization_date) VALUES ('utilization.pdf','2026-11-05') RETURNING utilization_cert_id")
            utilization_id = cursor.fetchone()[0]
            cursor.execute('UPDATE capstone SET copyright_cert_id=%s,utilization_cert_id=%s WHERE capstone_id=1',
                           (copyright_id, utilization_id))
            for column, table, certificate_id in (
                ('copyright_cert_id', 'copyright', copyright_id),
                ('utilization_cert_id', 'utilization', utilization_id),
            ):
                for statement, params, error in (
                    (sql.SQL('UPDATE capstone SET {}=%s WHERE capstone_id=2').format(sql.Identifier(column)), (certificate_id,), psycopg2.errors.UniqueViolation),
                    (sql.SQL('UPDATE capstone SET {}=%s WHERE capstone_id=2').format(sql.Identifier(column)), (-1,), psycopg2.errors.ForeignKeyViolation),
                    (sql.SQL('DELETE FROM {} WHERE {}=%s').format(sql.Identifier(table), sql.Identifier(column)), (certificate_id,), psycopg2.errors.RestrictViolation),
                ):
                    cursor.execute('SAVEPOINT certificate_constraint')
                    with pytest.raises(error):
                        cursor.execute(statement, params)
                    cursor.execute('ROLLBACK TO SAVEPOINT certificate_constraint')
        finally:
            conn.rollback()
            cursor.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
            conn.commit()
