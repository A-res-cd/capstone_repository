"""Session queries preserve identity, casing, and connection cleanup."""
from datetime import datetime, timezone

import pytest

from app.db import session_users


class Cursor:
    def __init__(self, row=None, error=None):
        self.row = row
        self.error = error
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def execute(self, query, params):
        self.query, self.params = query, params
        if self.error:
            raise self.error

    def fetchone(self):
        return self.row


class Connection:
    def __init__(self, cursor):
        self.value = cursor
        self.closed = False

    def cursor(self, **kwargs):
        return self.value

    def close(self):
        self.closed = True


def test_anonymous_user_needs_no_database(monkeypatch):
    monkeypatch.setattr(session_users, "db_connect", lambda: pytest.fail("Unexpected connection"))
    assert session_users.get_current_user(None) is None


def test_current_user_preserves_identity_and_role(monkeypatch):
    user = {"user_id": 12, "user_first_name": "Amy", "role_id": 1, "role_name": "Student"}
    cursor = Cursor(row=user)
    conn = Connection(cursor)
    monkeypatch.setattr(session_users, "db_connect", lambda: conn)
    assert session_users.get_current_user(12) == user
    assert cursor.params == (12,)
    assert cursor.closed and conn.closed


@pytest.mark.parametrize("row", [None, {"locked_until": None}, {"locked_until": datetime(2026, 9, 19, tzinfo=timezone.utc)}])
def test_lockout_lookup_preserves_case_insensitive_match(monkeypatch, row):
    cursor = Cursor(row=row)
    conn = Connection(cursor)
    monkeypatch.setattr(session_users, "db_connect", lambda: conn)
    assert session_users.get_locked_until("MiXeD") == (row["locked_until"] if row else None)
    assert cursor.params == ("MiXeD", "MiXeD")
    assert "LOWER(k.username) = LOWER(%s)" in cursor.query
    assert cursor.closed and conn.closed


@pytest.mark.parametrize("lookup,argument", [(session_users.get_current_user, 12), (session_users.get_locked_until, "Amy")])
def test_connection_released_when_query_fails(monkeypatch, lookup, argument):
    cursor = Cursor(error=RuntimeError("query failed"))
    conn = Connection(cursor)
    monkeypatch.setattr(session_users, "db_connect", lambda: conn)
    with pytest.raises(RuntimeError, match="query failed"):
        lookup(argument)
    assert cursor.closed and conn.closed
