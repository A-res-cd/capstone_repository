"""Reproducible SQL plans against an isolated database; never production data."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
from statistics import median
from threading import Barrier
from time import perf_counter
from unittest.mock import MagicMock, patch

import psycopg2
import pytest

from app.db import archive, capstone_requests, connection, keywords, qol, requests
from tests.test_original_branch_features import feature_db, isolated_database

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def performance_db(feature_db):
    with closing(feature_db()) as conn, conn.cursor() as cursor:
        cursor.execute((ROOT / 'migrations/20261011_capstone_requests.sql').read_text())
        cursor.execute((ROOT / 'migrations/20261009_normalize_capstone_keywords.sql').read_text())
        cursor.execute('''INSERT INTO "user" (role_id, user_first_name)
                          SELECT 1, 'Reader ' || n FROM generate_series(1, 1000) n''')
        cursor.execute('''INSERT INTO capstone (capstone_title, capstone_year)
                          SELECT 'Project ' || n, 2026 FROM generate_series(1, 4000) n''')
        cursor.execute('''INSERT INTO request (user_id, capstone_id, request_status,
                                              request_type, request_date, decision_date)
                          SELECT 1 + (n % 1000), 1 + (n % 4000), 'approved', 'manuscript',
                                 CURRENT_TIMESTAMP, CURRENT_TIMESTAMP - n * INTERVAL '1 second'
                          FROM generate_series(1, 50000) n''')
        cursor.execute('''INSERT INTO capstone_requests (capstone_id, user_id, requested_at)
                          SELECT 1 + (n % 4000), 1 + (n % 1000),
                                 CURRENT_TIMESTAMP - n * INTERVAL '1 second'
                          FROM generate_series(1, 16000) n''')
        cursor.execute('''INSERT INTO author (aut_first_name, aut_last_name)
                          SELECT 'Author', n::text FROM generate_series(1, 12000) n''')
        cursor.execute('''INSERT INTO capauth (capstone_id, author_id, role, author_order)
                          SELECT 1 + ((n - 1) / 3), n, 'Author', 1 + ((n - 1) % 3)
                          FROM generate_series(1, 12000) n''')
        index_file = ROOT / 'migrations/20261012_database_performance.sql'
        if index_file.exists():
            cursor.execute(index_file.read_text())
            cursor.execute(index_file.read_text())
        for table in ('request', 'capstone_requests', 'capstone', 'capauth', 'author'):
            cursor.execute(f'ANALYZE {table}')
        conn.commit()
    return feature_db


def capture(module, function, *args):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.__enter__.return_value = cursor
    cursor.fetchone.return_value = {'notifications': [], 'unread_count': 0,
                                  'manuscript_requests': 0, 'user_requests': 0}
    cursor.fetchall.return_value = []
    with patch.object(module, 'db_connect', return_value=conn):
        function(*args)
    return cursor.execute.call_args.args


def nodes(plan):
    yield plan
    for child in plan.get('Plans', []):
        yield from nodes(child)


def profile(cursor, sql, params):
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    plans = []
    for _ in range(5):
        cursor.execute('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ' + sql, params)
        plans.append(cursor.fetchone()[0][0])
    plan = plans[-1]['Plan']
    return rows, {
        'median_execution_ms': round(median(item['Execution Time'] for item in plans), 3),
        'shared_hit_blocks': plan.get('Shared Hit Blocks', 0),
        'author_aggregate_loops': max((node['Actual Loops'] for node in nodes(plan)
                                     if node['Node Type'] == 'Aggregate'), default=0),
        'request_scans': [{key: node.get(key) for key in
                          ('Node Type', 'Index Name', 'Actual Rows', 'Actual Loops', 'Rows Removed by Filter')}
                         for node in nodes(plan) if node.get('Relation Name') == 'request'],
    }


def test_query_plans_and_results(performance_db, tmp_path):
    baseline = json.loads((ROOT / 'tests/fixtures/database_queries_before.json').read_text())
    current = {
        'navigation': capture(qol, qol.get_page_nav_summary, 1, False, 6),
        'ranking': capture(capstone_requests, capstone_requests.get_most_requested_capstones, 5, 'all'),
    }
    report = {}
    with closing(performance_db()) as conn, conn.cursor() as cursor:
        dsn = conn.dsn
        for name, (sql, params) in current.items():
            original_rows, before = profile(cursor, baseline[name]['sql'], baseline[name]['params'])
            new_rows, after = profile(cursor, sql, params)
            assert new_rows == original_rows
            if name == 'navigation':
                assert sum(scan['Actual Rows'] * scan['Actual Loops'] for scan in after['request_scans']) <= 60
            else:
                assert after['author_aggregate_loops'] <= 5
            report[name] = {'before': before, 'after': after}
        sql, params = capture(requests, requests.get_approved_capstone_ids, 1, [1, 1001, 2001, 3001])
        approved, approval_plan = profile(cursor, sql, params)
        assert {row[0] for row in approved} == {1, 1001, 2001, 3001}
        assert sum(scan['Actual Rows'] * scan['Actual Loops'] for scan in approval_plan['request_scans']) <= 50
        report['approval_membership'] = approval_plan
    # Bounded read-only load; every worker owns a distinct transaction/connection.
    pool = psycopg2.pool.ThreadedConnectionPool(4, 4, dsn=dsn)
    try:
        for name, (sql, params) in current.items():
            for phase, query, values in [('before', baseline[name]['sql'], baseline[name]['params']),
                                         ('after', sql, params)]:
                barrier = Barrier(4)
                def read_worker(_):
                    conn = pool.getconn()
                    try:
                        barrier.wait(timeout=10)
                        with conn.cursor() as cursor:
                            for _ in range(10):
                                cursor.execute(query, values)
                                cursor.fetchall()
                        conn.rollback()
                    finally:
                        pool.putconn(conn)
                start = perf_counter()
                with ThreadPoolExecutor(max_workers=4) as workers:
                    list(workers.map(read_worker, range(4)))
                report[name][phase]['queries_per_second_4_workers'] = round(40 / (perf_counter() - start), 1)
    finally:
        pool.closeall()
    (tmp_path / 'database_performance.json').write_text(json.dumps(report, indent=2))
    print('\nDATABASE_PERFORMANCE ' + json.dumps(report, sort_keys=True))


def test_admin_navigation_sql_contract_is_preserved():
    baseline = json.loads((ROOT / 'tests/fixtures/database_queries_before.json').read_text())['navigation']
    sql, params = capture(qol, qol.get_page_nav_summary, 1, True, 6)
    assert ' '.join(sql.split()) == ' '.join(baseline['sql'].split())
    assert params == (1, 6, 1, True, True)


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


def test_archive_filters_and_approval_membership(feature_db, monkeypatch):
    monkeypatch.setattr(archive, 'db_connect', feature_db)
    monkeypatch.setattr(requests, 'db_connect', feature_db)
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
        cursor.executemany('''INSERT INTO request (user_id, capstone_id, request_status, request_date)
                              VALUES (%s, %s, %s, CURRENT_TIMESTAMP)''',
                           [(first, ids[0], 'approved'), (first, ids[0], 'approved'),
                            (first, ids[1], 'pending'), (second, ids[1], 'approved'),
                            (first, ids[2], 'approved')])
        conn.commit()
    years, programs, specializations = archive.get_archive_filters()
    assert years == archive.get_archive_years() == [2026, 2025]
    assert (program_id, 'IT') in programs
    assert (specialization_id, 'Web') in specializations
    history = requests.get_user_requests(first)
    expected = {row['capstone_id'] for row in history if row['request_status'] == 'approved'} & set(ids[:2])
    assert set(requests.get_approved_capstone_ids(first, ids[:2])) == expected == {ids[0]}
    monkeypatch.setattr(requests, 'db_connect', lambda: pytest.fail('Empty page must not query approvals'))
    assert requests.get_approved_capstone_ids(first, []) == []


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
