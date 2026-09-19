"""Protect public endpoints while organizing their implementation by feature."""
import json
from pathlib import Path

from flask import Flask
import pytest

from app.routes import blueprints


@pytest.fixture
def route_app():
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY="route-contract-test")
    for blueprint in blueprints:
        app.register_blueprint(blueprint)
    return app


def test_all_urls_endpoints_and_methods_survive_split(route_app):
    expected = json.loads((Path(__file__).parent / "fixtures/route_contract.json").read_text(encoding="utf-8"))
    actual = sorted([rule.rule, rule.endpoint, sorted(rule.methods)] for rule in route_app.url_map.iter_rules())
    assert actual == expected


@pytest.mark.parametrize("path", [
    "/repository", "/analytics", "/analytics/report.xlsx", "/audit-logs",
    "/manage_users", "/requests", "/recyclebin", "/repository/pdf/1",
    "/archive", "/user-info", "/my-requests", "/propose-topic",
])
def test_protected_features_still_redirect_anonymous_users(route_app, path):
    response = route_app.test_client().get(path)
    assert response.status_code == 302
    assert response.location == "/signin"
