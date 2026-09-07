from importlib import import_module
from pathlib import Path

from flask import Flask, jsonify

pages_routes = import_module("app.routes.pages")
main_routes = import_module("app.routes.main")
ROOT = Path(__file__).resolve().parents[2]


def test_profile_overview_passes_preview_works_to_template(monkeypatch):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "user-capstone-test"
    app.register_blueprint(pages_routes.pages)

    monkeypatch.setattr(
        pages_routes,
        "get_own_profile",
        lambda user_id: {
            "user_first_name": "Maria",
            "user_last_name": "Cruz",
            "role_name": "Student",
        },
    )
    monkeypatch.setattr(pages_routes, "get_user_contacts", lambda user_id: [])
    monkeypatch.setattr(pages_routes, "get_all_roles", lambda: [])
    monkeypatch.setattr(pages_routes, "get_own_promotion_requests", lambda user_id: [])
    monkeypatch.setattr(
        pages_routes,
        "render_template",
        lambda template, **context: jsonify({
            "template": template,
            "my_works": context["my_works"],
        }),
    )

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = 7
        response = client.get("/profile")

    assert response.status_code == 200
    assert response.json["template"] == "global/profile.html"
    assert response.json["my_works"][0]["title"] == "Fraud Detection in Financial Transactions Using Deep Learning"


def test_profile_overview_template_renders_capstones(monkeypatch):
    app = Flask(__name__, template_folder=str(ROOT / "app/templates"))
    app.config["SECRET_KEY"] = "profile-template-test"
    app.jinja_env.globals["csrf_token"] = lambda: ""
    app.register_blueprint(main_routes.main)
    app.register_blueprint(pages_routes.pages)

    monkeypatch.setattr(
        pages_routes,
        "get_own_profile",
        lambda user_id: {
            "user_first_name": "Maria",
            "user_last_name": "Cruz",
            "role_name": "Student",
            "account_status": "active",
            "username": "mcruz",
            "university_no": "2021-00123",
        },
    )
    monkeypatch.setattr(pages_routes, "get_user_contacts", lambda user_id: [])
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = 7
        response = client.get("/profile")

    assert response.status_code == 200
    assert b"Profile Overview" in response.data
    assert b"My Works" in response.data
    assert b"Preview data" in response.data
