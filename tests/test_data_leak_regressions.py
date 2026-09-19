from app.db import users
from app.db.connection import _PooledConnection


class RecordingCursor:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((" ".join(query.split()), params))

    def fetchall(self):
        return [(11, 21), (11, 22)]


def test_delete_cascade_uses_caller_cursor_and_removes_private_data(monkeypatch):
    cursor = RecordingCursor()
    monkeypatch.setattr(
        users,
        "db_connect",
        lambda: (_ for _ in ()).throw(AssertionError("unexpected connection")),
    )

    users._run_delete_cascade(cursor, user_id=7, acting_id=3)

    statements = [query for query, _ in cursor.calls]
    assert any("DELETE FROM password_reset" in query for query in statements)
    assert any("DELETE FROM kappa" in query for query in statements)
    assert any("DELETE FROM ror" in query for query in statements)
    assert statements.index(next(q for q in statements if "DELETE FROM password_reset" in q)) < statements.index(
        next(q for q in statements if "DELETE FROM contact" in q)
    )


class FakeConnection:
    closed = False
    status = 1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class FakePool:
    def __init__(self):
        self.returned = []

    def putconn(self, connection, close=False):
        self.returned.append((connection, close))


def test_pooled_connection_context_returns_connection_to_pool():
    pool = FakePool()
    connection = FakeConnection()

    with _PooledConnection(pool, connection):
        pass

    assert pool.returned == [(connection, False)]
