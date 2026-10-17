from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import psycopg2
from playwright.sync_api import expect

from app.db import capstone_requests, requests as request_db
from app.routes.pages import archive, manuscripts
from tests.test_original_branch_features import feature_app, feature_db, isolated_database, login

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def ranking_db(feature_db, monkeypatch):
    with closing(feature_db()) as conn, conn.cursor() as cursor:
        sql = (ROOT / 'migrations/20261011_capstone_requests.sql').read_text(encoding='utf-8')
        cursor.execute(sql)
        cursor.execute(sql)  # Additive migration is repeatable.
        conn.commit()
    monkeypatch.setattr(capstone_requests, 'db_connect', feature_db)
    monkeypatch.setattr(request_db, 'db_connect', feature_db)
    return feature_db


def seed(connect):
    with closing(connect()) as conn, conn.cursor() as cursor:
        cursor.execute('INSERT INTO "user" (role_id, user_first_name, account_status) VALUES (1, \'Reader\', \'active\') RETURNING user_id')
        user_id = cursor.fetchone()[0]
        ids = []
        for title in ('Alpha', 'Beta', 'Gamma'):
            cursor.execute('INSERT INTO capstone (capstone_title, capstone_year) VALUES (%s, 2026) RETURNING capstone_id', (title,))
            ids.append(cursor.fetchone()[0])
        conn.commit()
    return user_id, ids


def add_events(connect, events, user_id=None):
    with closing(connect()) as conn, conn.cursor() as cursor:
        cursor.executemany('INSERT INTO capstone_requests (capstone_id, user_id, requested_at) VALUES (%s, %s, %s)',
                           [(capstone_id, user_id, when) for capstone_id, when in events])
        conn.commit()


def record(connect, capstone_id, user_id):
    with closing(connect()) as conn, conn.cursor() as cursor:
        counted = capstone_requests.record_capstone_request(cursor, capstone_id, user_id)
        conn.commit()
        return counted


def test_order_ties_limit_and_authors_do_not_multiply_counts(ranking_db):
    _, (alpha, beta, gamma) = seed(ranking_db)
    now = datetime.now(timezone.utc)
    add_events(ranking_db, [(alpha, now - timedelta(days=2)), (alpha, now - timedelta(days=1)),
                           (beta, now - timedelta(days=3)), (beta, now - timedelta(days=2)),
                           (beta, now - timedelta(days=1)), (gamma, now - timedelta(days=2)), (gamma, now)])
    with closing(ranking_db()) as conn, conn.cursor() as cursor:
        for first, role, order in [('Second', 'Author', 2), ('First', 'Author', 1), ('Adviser', 'Adviser', 3)]:
            cursor.execute("INSERT INTO author (aut_first_name, aut_last_name) VALUES (%s, 'Writer') RETURNING author_id", (first,))
            cursor.execute('INSERT INTO capauth (capstone_id, author_id, role, author_order) VALUES (%s, %s, %s, %s)',
                           (beta, cursor.fetchone()[0], role, order))
        conn.commit()
    rows = capstone_requests.getMostRequestedCapstones()
    assert [row['capstone_id'] for row in rows] == [beta, gamma, alpha]
    assert [row['request_count'] for row in rows] == [3, 2, 2]
    assert rows[0]['authors'] == 'First Writer, Second Writer'
    assert rows[0]['capstone_year'] == 2026
    assert [row['capstone_id'] for row in capstone_requests.get_most_requested_capstones(limit=2)] == [beta, gamma]


@pytest.mark.parametrize('period,counts', [('all', [3, 1]), ('30d', [2, 1]), ('7d', [1])])
def test_period_filter(ranking_db, period, counts):
    _, (alpha, beta, _) = seed(ranking_db)
    now = datetime.now(timezone.utc)
    add_events(ranking_db, [(alpha, now - timedelta(days=1)), (alpha, now - timedelta(days=8)),
                           (alpha, now - timedelta(days=31)), (beta, now - timedelta(days=10))])
    rows = capstone_requests.get_most_requested_capstones(period=period)
    assert [row['request_count'] for row in rows] == counts


def test_empty_and_archived_deleted_capstones(ranking_db):
    assert capstone_requests.get_most_requested_capstones() == []
    _, (alpha, beta, gamma) = seed(ranking_db)
    add_events(ranking_db, [(project, datetime.now(timezone.utc)) for project in (alpha, beta, gamma)])
    with closing(ranking_db()) as conn, conn.cursor() as cursor:
        cursor.execute('UPDATE capstone SET is_archived = TRUE WHERE capstone_id = %s', (alpha,))
        cursor.execute('DELETE FROM capstone WHERE capstone_id = %s', (beta,))
        conn.commit()
    assert [row['capstone_id'] for row in capstone_requests.get_most_requested_capstones()] == [gamma]
    with closing(ranking_db()) as conn, conn.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) FROM capstone_requests WHERE capstone_id = %s', (beta,))
        assert cursor.fetchone()[0] == 0


def test_duplicate_hour_other_user_and_concurrent_requests(ranking_db):
    user_id, (alpha, _, _) = seed(ranking_db)
    with ThreadPoolExecutor(max_workers=2) as pool:
        counted = list(pool.map(lambda _: record(ranking_db, alpha, user_id), range(2)))
    assert sum(counted) == 1
    assert not record(ranking_db, alpha, user_id)
    with closing(ranking_db()) as conn, conn.cursor() as cursor:
        cursor.execute("UPDATE capstone_requests SET requested_at = CURRENT_TIMESTAMP - INTERVAL '61 minutes'")
        cursor.execute('INSERT INTO "user" (role_id) VALUES (1) RETURNING user_id')
        other_user = cursor.fetchone()[0]
        conn.commit()
    assert record(ranking_db, alpha, user_id)
    assert record(ranking_db, alpha, other_user)
    assert capstone_requests.get_most_requested_capstones()[0]['request_count'] == 3


def test_deleted_user_preserves_counts(ranking_db):
    user_id, (alpha, _, _) = seed(ranking_db)
    assert record(ranking_db, alpha, user_id)
    with closing(ranking_db()) as conn, conn.cursor() as cursor:
        cursor.execute('DELETE FROM "user" WHERE user_id = %s', (user_id,))
        conn.commit()
    assert capstone_requests.get_most_requested_capstones()[0]['request_count'] == 1


def test_real_submission_duplicate_cancel_and_resubmit(ranking_db, feature_app):
    user_id, (alpha, beta, _) = seed(ranking_db)
    client = feature_app.test_client()
    login(client, 1)
    with client.session_transaction() as state:
        state['user_id'] = user_id
    data = {'request_purpose': 'Literature review'}
    for _ in range(2):
        assert client.post(f'/request_manuscript/{alpha}', data=data).status_code == 302
    assert capstone_requests.get_most_requested_capstones()[0]['request_count'] == 1
    with closing(ranking_db()) as conn, conn.cursor() as cursor:
        cursor.execute("UPDATE request SET request_status = 'cancelled' WHERE capstone_id = %s", (alpha,))
        conn.commit()
    client.post(f'/request_manuscript/{alpha}', data=data)
    assert capstone_requests.get_most_requested_capstones()[0]['request_count'] == 1
    # Validation failure creates neither a manuscript request nor a ranking event.
    client.post(f'/request_manuscript/{beta}', data={'request_purpose': 'forged'})
    assert len(capstone_requests.get_most_requested_capstones()) == 1


def test_tracking_failure_rolls_back_submission(ranking_db, monkeypatch):
    user_id, (alpha, _, _) = seed(ranking_db)

    def fail(*args):
        raise RuntimeError('tracking failed')

    monkeypatch.setattr(request_db, 'record_capstone_request', fail)
    assert not request_db.request_fullview(user_id, alpha, 'Literature review')[0]
    with closing(ranking_db()) as conn, conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM request WHERE request_type = 'manuscript'")
        assert cursor.fetchone()[0] == 0


def test_archived_missing_requests_not_accepted(ranking_db):
    user_id, (alpha, _, _) = seed(ranking_db)
    with closing(ranking_db()) as conn, conn.cursor() as cursor:
        cursor.execute('UPDATE capstone SET is_archived = TRUE WHERE capstone_id = %s', (alpha,))
        conn.commit()
    assert not request_db.request_fullview(user_id, alpha, 'Reference')[0]
    assert not request_db.request_fullview(user_id, 99999, 'Reference')[0]
    assert capstone_requests.get_most_requested_capstones() == []


@pytest.mark.parametrize('limit,period', [(0, 'all'), (51, 'all'), (True, 'all'), (1, 'year'), ('5', 'all')])
def test_service_rejects_invalid_options(limit, period):
    with pytest.raises(ValueError):
        capstone_requests.get_most_requested_capstones(limit, period)


def test_api_login_validation_empty_and_populated(ranking_db, feature_app):
    client = feature_app.test_client()
    assert client.get('/capstones/most-requested').location == '/signin'
    login(client, 1)
    assert client.get('/capstones/most-requested').json == {'capstones': [], 'limit': 5, 'period': 'all'}
    for query in ('limit=0', 'limit=51', 'limit=abc', 'period=invalid'):
        assert client.get('/capstones/most-requested?' + query).status_code == 400
    _, (alpha, _, _) = seed(ranking_db)
    add_events(ranking_db, [(alpha, datetime.now(timezone.utc))])
    for _ in range(2):
        response = client.get('/capstones/most-requested?limit=1&period=7d')
        assert response.status_code == 200
        row = response.json['capstones'][0]
        assert row['request_count'] == 1 and row['detail_url'] == f'/repository/pdf/{alpha}'
        assert 'user_id' not in row


@pytest.mark.parametrize('width', [1280, 390])
def test_separate_rankings_page_and_archive_filters(ranking_db, feature_app, page, monkeypatch, width):
    client = feature_app.test_client()
    login(client, 1)
    captured = []

    def results(**filters):
        captured.append(filters)
        return [], 0

    monkeypatch.setattr(archive, 'get_archive_capstones', results)
    monkeypatch.setattr(archive, 'get_archive_filters', lambda: ([2026], [], []))
    monkeypatch.setattr(archive, 'get_approved_capstone_ids', lambda *_: [])
    monkeypatch.setattr(manuscripts, 'get_user_requests', lambda _: [])
    ranking_calls = []
    ranking_query = archive.get_most_requested_capstones

    def rankings():
        ranking_calls.append(True)
        return ranking_query()

    monkeypatch.setattr(archive, 'get_most_requested_capstones', rankings)

    def handle(route):
        url = urlsplit(route.request.url)
        if url.netloc != 'rankings.test':
            route.abort()
            return
        response = client.get(url.path + ('?' + url.query if url.query else ''))
        route.fulfill(status=response.status_code, body=response.data, headers=dict(response.headers))

    page.route('**/*', handle)
    page.set_viewport_size({'width': width, 'height': 900})
    page.goto('http://rankings.test/archive?search=web&year=2026&sort=title')
    expect(page.locator('.most-requested')).to_have_count(0)
    assert not ranking_calls
    assert captured[-1]['search'] == 'web' and captured[-1]['year'] == '2026' and captured[-1]['sort'] == 'title'
    page.goto('http://rankings.test/most-requested')
    expect(page.get_by_text('No requests yet', exact=True)).to_be_visible()
    _, (alpha, _, _) = seed(ranking_db)
    add_events(ranking_db, [(alpha, datetime.now(timezone.utc))])
    page.reload()
    card = page.locator('.most-requested-card')
    expect(card).to_be_visible()
    expect(card).to_contain_text('Alpha')
    expect(card).to_contain_text('2026')
    expect(card).to_contain_text('1 request')
    expect(card).to_have_attribute('href', f'/repository/pdf/{alpha}')
    expect(page.locator('.archive-filters')).to_have_count(0)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')


def test_rankings_page_login_and_unavailable_state(feature_app, monkeypatch):
    client = feature_app.test_client()
    assert client.get('/most-requested').location == '/signin'
    login(client, 1)

    def unavailable():
        raise psycopg2.OperationalError('unavailable')

    monkeypatch.setattr(archive, 'get_most_requested_capstones', unavailable)
    response = client.get('/most-requested')
    assert response.status_code == 200
    assert b'Request rankings are temporarily unavailable.' in response.data


@pytest.mark.parametrize('role', ['Admin', 'Capstone Professor', 'Faculty', 'Student'])
def test_rankings_navigation(feature_app, role):
    from app.constants.nav import get_nav_links
    from flask import url_for

    with feature_app.test_request_context():
        links, _ = get_nav_links(role)
        link = next(link for link in links if link['name'] == 'Most Requested Capstones')
        assert url_for(link['url']) == '/most-requested'
