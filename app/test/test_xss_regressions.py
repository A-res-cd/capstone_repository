from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_topic_titles_are_rendered_as_text_not_html():
    source = (ROOT / "app/static/js/propose_topic.js").read_text(encoding="utf-8")

    assert "title.textContent = String(m.capstone_title" in source
    assert "${m.capstone_title}" not in source
    assert "li.innerHTML" not in source


def test_spa_navigation_does_not_eval_page_scripts():
    source = (ROOT / "app/static/js/navigation.js").read_text(encoding="utf-8")

    assert "new Function" not in source
    assert ".innerHTML" not in source


def test_security_headers_limit_script_sources(monkeypatch):
    monkeypatch.setenv("FLASK_DEBUG", "1")

    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    response = app.test_client().get("/")

    policy = response.headers["Content-Security-Policy"]
    assert "object-src 'none'" in policy
    assert "base-uri 'self'" in policy
    assert "unsafe-eval" not in policy
    assert response.headers["X-Content-Type-Options"] == "nosniff"
