from pathlib import Path
from importlib import import_module

from flask import Flask

from app.db import health


main_routes = import_module("app.routes.main")


class HealthCursor:
    def __init__(self, tables, applied):
        self.tables = tables
        self.applied = applied
        self.closed = False

    def execute(self, query, params=None):
        self.query = query

    def fetchone(self):
        return self.tables

    def fetchall(self):
        return self.applied

    def close(self):
        self.closed = True


class HealthConnection:
    def __init__(self, cursor):
        self.cursor_value = cursor
        self.closed = False

    def cursor(self):
        return self.cursor_value

    def close(self):
        self.closed = True


def test_database_is_ready_when_schema_and_migrations_match(monkeypatch):
    cursor = HealthCursor(
        ("user", "capstone", "schema_migration"),
        [("001.sql", "checksum")],
    )
    connection = HealthConnection(cursor)
    monkeypatch.setattr(health, "db_connect", lambda: connection)
    monkeypatch.setattr(health, "migration_files", lambda: [Path("001.sql")])
    monkeypatch.setattr(health, "migration_checksum", lambda path: "checksum")

    assert health.database_is_ready()
    assert cursor.closed and connection.closed


def test_database_is_not_ready_when_a_migration_is_pending(monkeypatch):
    cursor = HealthCursor(
        ("user", "capstone", "schema_migration"),
        [],
    )
    connection = HealthConnection(cursor)
    monkeypatch.setattr(health, "db_connect", lambda: connection)
    monkeypatch.setattr(health, "migration_files", lambda: [Path("001.sql")])
    monkeypatch.setattr(health, "migration_checksum", lambda path: "checksum")

    assert not health.database_is_ready()


def test_health_routes_expose_only_probe_status(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(main_routes.main)
    monkeypatch.setattr(main_routes, "database_is_ready", lambda: False)

    with app.test_client() as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")

    assert live.status_code == 200
    assert live.json == {"status": "ok"}
    assert ready.status_code == 503
    assert ready.json == {"status": "not_ready"}
