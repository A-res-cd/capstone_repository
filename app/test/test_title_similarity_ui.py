from pathlib import Path

import pytest
from jinja2 import ChoiceLoader, DictLoader, Environment, FileSystemLoader

from app.services.recommender import TopicRecommender


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def topic_page(page):
    # Use the application layout containers without a database connection.
    env = Environment(loader=ChoiceLoader([
        DictLoader({"base.html": (
            '<!doctype html><html><body><header class="header" style="height:51px">Title Similarity</header>'
            '<div class="layout"><div class="main-wrapper"><main id="page-content">'
            '{% block content %}{% endblock %}</main></div></div></body></html>'
        )}),
        FileSystemLoader(ROOT / "app/templates"),
    ]), autoescape=True)
    html = env.get_template("global/propose_title.html").render(url_for=lambda *args, **kwargs: "/abstract/0")
    for stylesheet in ("pages/_propose-topic.css", "base/global.css", "base/root.css"):
        page.route(
            f"**/static/css/{stylesheet}",
            lambda route, request, stylesheet=stylesheet: route.fulfill(path=ROOT / "app/static/css" / stylesheet, content_type="text/css"),
        )
    page.route("http://capre.test/propose-topic", lambda route: route.fulfill(body=html, content_type="text/html"))
    page.goto("http://capre.test/propose-topic")
    page.add_style_tag(url="http://capre.test/static/css/base/global.css")
    page.add_style_tag(url="http://capre.test/static/css/pages/_propose-topic.css")
    page.add_script_tag(path=str(ROOT / "app/static/js/propose_topic.js"))
    page.evaluate("document.dispatchEvent(new Event('DOMContentLoaded'))")
    return page


def test_title_input_and_reset(topic_page):
    from playwright.sync_api import expect

    page = topic_page
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    payloads = []
    corpus = [{"capstone_id": 1, "capstone_title": "Orchard Sensor Sensor", "specialization_name": "Agriculture"}]

    def respond(route):
        payload = route.request.post_data_json
        payloads.append(payload)
        matches = TopicRecommender(corpus).find_similar(payload["title"])
        route.fulfill(json={"matches": matches})

    page.route("**/api/topic-similarity", respond)
    expect(page.locator("#pt-keywords")).to_have_count(0)
    expect(page.locator("#pt-mode")).to_have_count(0)
    page.locator("#pt-title").fill("Orchard Sensor Sensor")
    expect(page.locator(".pt-badge").last).to_have_text("High overlap · 100%")
    assert payloads[-1] == {"title": "Orchard Sensor Sensor"}
    expect(page.locator("#pt-results-label")).to_have_text("Similar titles")
    expect(page.locator(".pt-match")).to_have_count(1)
    page.locator("#pt-title").fill("Marine Conservation")
    expect(page.locator("#pt-status")).to_contain_text("Different wording")
    page.locator("#pt-title").clear()
    expect(page.locator("#pt-list")).to_be_hidden()
    expect(page.locator("#pt-readiness-similarity")).to_have_text("Waiting for a title")
    page.locator("#pt-title").press("Enter")
    assert page.url == "http://capre.test/propose-topic"
    assert errors == []


def test_api_failure_is_shown_as_unavailable(topic_page):
    from playwright.sync_api import expect

    page = topic_page
    page.route("**/api/topic-similarity", lambda route: route.fulfill(status=500, json={"error": "Unavailable"}))
    page.locator("#pt-title").fill("Orchard Sensor Sensor")
    expect(page.locator("#pt-readiness-similarity")).to_have_text("Check unavailable")
    expect(page.locator("#pt-empty")).to_be_visible()
    expect(page.locator("#pt-list")).to_be_hidden()
