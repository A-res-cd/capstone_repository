from importlib import import_module
from pathlib import Path

from flask import Flask, render_template, session
from jinja2 import ChoiceLoader, DictLoader
from playwright.sync_api import expect
import pytest

from app.routes.forms import CreateCapstoneForm

ROOT = Path(__file__).resolve().parents[2]
admin_routes = import_module("app.routes.admin")


@pytest.fixture
def repository_page(page):
    app = Flask(__name__, template_folder=str(ROOT / "app/templates"))
    app.config.update(SECRET_KEY="author-selector-test", WTF_CSRF_ENABLED=False)
    app.jinja_env.globals["csrf_token"] = lambda: ""
    app.register_blueprint(admin_routes.admin)
    app.jinja_loader = ChoiceLoader([
        DictLoader({"base.html": '<!doctype html><html><head><meta charset="utf-8"></head><body>{% block content %}{% endblock %}</body></html>'}),
        app.jinja_loader,
    ])
    with app.test_request_context():
        session["role_name"] = "Admin"
        form = CreateCapstoneForm()
        form.program_id.choices = [(1, "Information Technology")]
        form.specialization_id.choices = [(1, "Data Science")]
        for author in form.authors:
            author.user_id.choices = [(0, "No linked account"), (1, "Maria Cruz · Account #1"), (2, "Maria Cruz · Account #2")]
        html = render_template("admin/repository.html", form=form, programs=[(1, "IT")],
                               specializations=[(1, "Data Science")], total_pages=1, capstones=[{
                                   "capstone_id": 1, "capstone_title": "Linked Work", "capstone_year": 2026,
                                   "capstone_keywords": "research", "program_id": 1, "specialization_id": 1,
                                   "semester": "1st Semester", "capstone_file": "sample.pdf",
                               }])
    page.route("http://capre.test/repository", lambda route: route.fulfill(body=html, content_type="text/html"))
    page.route("**/static/**", lambda route: route.fulfill(path=ROOT / "app/static" / route.request.url.split("/static/", 1)[1]))
    page.goto("http://capre.test/repository")
    for stylesheet in ("base/root.css", "base/global.css", "components/_forms.css", "components/_buttons.css", "components/_custom-select.css", "pages/_user-information.css", "pages/_repository.css"):
        page.add_style_tag(url=f"http://capre.test/static/css/{stylesheet}")
    page.add_script_tag(path=str(ROOT / "app/static/js/custom_select.js"))
    page.add_script_tag(path=str(ROOT / "app/static/js/repository.js"))
    page.evaluate("document.dispatchEvent(new Event('DOMContentLoaded'))")
    return page


PEOPLE = {"success": True, "authors": [{"author_id": 11, "user_id": 1, "first": "Maria", "last": "Cruz"}],
          "adviser": {"author_id": 12, "first": "Jane", "last": "Adviser"}}


def test_edit_reload_and_create_preserve_only_correct_links(repository_page):
    page = repository_page
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("**/repository/1/people", lambda route: route.fulfill(json=PEOPLE))
    page.locator(".btn-row--edit").click()
    expect(page.locator("#authors-0-user_id")).to_have_value("1")
    author_select = page.locator("#authors-0-user_id").locator("..").locator(".custom-select__input")
    expect(author_select).to_have_value("Maria Cruz · Account #1")
    expect(page.get_by_role("combobox", name="Program", exact=False).last).to_have_value("IT")
    expect(page.locator("#authors-0-author_id")).to_have_value("11")
    expect(page.locator("#adviser-author_id")).to_have_value("12")
    page.locator("#authors-0-user_id").evaluate("el => { el.value = '2'; }")
    page.locator("#btn-reset").click()
    expect(page.locator("#authors-0-user_id")).to_have_value("1")
    expect(author_select).to_have_value("Maria Cruz · Account #1")
    page.locator("#btn-cancel").click()
    page.locator("#btn-open-create").click()
    expect(page.locator("#authors-0-user_id")).to_have_value("0")
    expect(author_select).to_have_value("No linked account")
    expect(page.locator("#authors-0-author_id")).to_have_value("")
    expect(page.locator("#adviser-author_id")).to_have_value("")
    assert errors == []


def test_failed_or_stale_people_fetch_cannot_clear_or_replace_links(repository_page):
    page = repository_page
    page.route("**/repository/1/people", lambda route: route.fulfill(status=503, json={"success": False}))
    page.locator(".btn-row--edit").click()
    expect(page.locator("#people-load-status")).to_contain_text("Close and reopen")
    expect(page.locator("#btn-submit")).to_be_disabled()
    page.locator("#btn-cancel").click()
    pending = []
    page.route("**/repository/1/people", lambda route: pending.append(route))
    page.locator(".btn-row--edit").click()
    expect(page.locator("#btn-submit")).to_be_disabled()
    page.locator("#btn-cancel").click()
    page.locator("#btn-open-create").click()
    assert pending
    with page.expect_response("**/repository/1/people"):
        pending[0].fulfill(json=PEOPLE)
    expect(page.locator("#authors-0-user_id")).to_have_value("0")
    expect(page.locator("#authors-0-author_id")).to_have_value("")


@pytest.mark.parametrize("width,dark", [(1322, False), (390, False), (390, True)])
def test_author_selector_stays_inside_themed_form(repository_page, width, dark):
    page = repository_page
    page.set_viewport_size({"width": width, "height": 850})
    if dark:
        page.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
    page.route("**/repository/1/people", lambda route: route.fulfill(json=PEOPLE))
    page.locator(".btn-row--edit").click()
    expect(page.locator("#authors-0-user_id")).to_have_value("1")
    page.evaluate("document.querySelectorAll('.form-step').forEach(el => el.classList.toggle('form-step--hidden', el.dataset.step !== '2'))")
    selector = page.locator("#authors-0-user_id").locator("..").get_by_role("combobox")
    expect(selector).to_be_visible()
    assert "author-account-help" in selector.get_attribute("aria-describedby")
    assert selector.evaluate("el => el.getBoundingClientRect().right <= window.innerWidth")
    assert selector.evaluate("el => getComputedStyle(el).backgroundColor") == page.locator("#authors-0-first_name").evaluate("el => getComputedStyle(el).backgroundColor")
