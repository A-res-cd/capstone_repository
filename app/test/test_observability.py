import json
from importlib import import_module
from types import SimpleNamespace

from flask import Flask

from app.utils.observability import finish_request_observation, start_request_observation


def test_request_observation_adds_id_and_does_not_log_query_values(caplog):
    app = Flask(__name__)
    app.before_request(start_request_observation)
    app.after_request(finish_request_observation)

    @app.get("/probe")
    def probe():
        return "ok"

    with caplog.at_level("INFO", logger="capre.http"):
        response = app.test_client().get("/probe?secret=do-not-log")

    assert response.status_code == 200
    assert len(response.headers["X-Request-ID"]) == 24
    message = next(record.getMessage() for record in caplog.records if record.name == "capre.http")
    payload = json.loads(message.split(" ", 1)[1])
    assert payload["path"] == "/probe"
    assert payload["status"] == 200
    assert "do-not-log" not in message


def test_preflight_configuration_requires_production_controls(monkeypatch):
    preflight = import_module("scripts.preflight")
    production = SimpleNamespace(
        UPLOAD_ANTIVIRUS_REQUIRED=True,
        UPLOAD_ANTIVIRUS_COMMAND="clamscan",
        UPLOAD_RETENTION_CLEANUP_ENABLED=True,
        UPLOAD_ORPHAN_RETENTION_DAYS=30,
        UPLOAD_ANTIVIRUS_TIMEOUT_SECONDS=30,
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        MAX_CONTENT_LENGTH=1024,
    )
    monkeypatch.setattr(preflight, "_scanner_available", lambda command: True)
    monkeypatch.setattr(preflight, "_command_available", lambda command: True)

    assert preflight.configuration_failures(production, {"FLASK_DEBUG": "0"}) == []
    assert preflight.configuration_failures(production, {"FLASK_DEBUG": "1"})
