"""Browser coverage for shared dropdowns, without a database or CDN."""
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect

ROOT = Path(__file__).resolve().parents[2]
HTML = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/static/css/base/global.css">
<link rel="stylesheet" href="/static/css/components/index.css">
</head><body><main id="page-content">
<form id="sample"><fieldset id="fields" style="border:0; min-width:0">
<div class="form-group"><label for="student">Student account</label>
<select id="student" name="student" data-custom-select="search" required aria-describedby="student-help">
<option value="" disabled selected>Choose a student</option>
<optgroup label="Verified students"><option value="1">Amy &amp; Team</option>
<option value="2">Ben Santos — Account #2</option><option value="3" disabled>Chris (unavailable)</option></optgroup>
<optgroup label="Unavailable" disabled><option value="4">Dana</option></optgroup>
<option value="5" hidden>Hidden student</option></select>
<span id="student-help">Check the exact account before assigning.</span></div>
<div class="form-group"><label for="program">Program</label>
<select id="program" name="program">
<option value="it">Information Technology</option><option value="disabled" disabled>Unavailable</option>
<option value="cs">Computer Science</option><option value="is">Information Systems</option></select></div>
</fieldset><button type="submit">Save selection</button><button type="reset">Reset form</button></form>
<label for="plain">Native select</label><select id="plain" data-native-select><option>Untouched</option></select>
<label for="multiple">Multiple select</label><select id="multiple" data-custom-select multiple><option>Untouched</option></select>
<a href="/next" id="next" style="position:fixed; top:4px; right:8px">Next page</a>
</main><script src="/static/js/custom_select.js"></script>
<script src="/static/js/navigation.js"></script></body></html>"""


@pytest.fixture
def dropdown_page(page):
    page.set_default_timeout(7000)
    def assets(route):
        path = urlsplit(route.request.url).path
        if path.startswith("/static/"):
            route.fulfill(path=ROOT / "app" / path.lstrip("/"))
        else:
            route.abort()

    page.route("**/*", assets)
    page.route("http://capre.test/select", lambda route: route.fulfill(body=HTML, content_type="text/html"))
    page.route("http://capre.test/next", lambda route: route.fulfill(
        body=HTML.replace('<form id="sample">', '<h1>Next page</h1><form id="sample">'), content_type="text/html"))
    page.goto("http://capre.test/select")
    page.add_style_tag(content="*,*::before,*::after { transition:none!important; animation:none!important; }")
    page.evaluate("""() => {
        window.events = []; window.submits = 0;
        for (const type of ['input', 'change']) document.querySelector('#student').addEventListener(type, e => events.push(type + ':' + e.target.value));
        document.querySelector('#sample').addEventListener('submit', e => {e.preventDefault(); window.submits++;});
    }""")
    return page


def test_search_selection_keeps_native_values_labels_and_events(dropdown_page):
    page = dropdown_page
    combo = page.get_by_role("combobox", name="Student account", exact=True)
    page.locator('label', has_text="Student account").click()
    expect(combo).to_be_focused()
    # Typing while closed opens and filters without losing the first character.
    combo.fill("Ben")
    expect(page.get_by_role("option", name="Ben Santos — Account #2")).to_be_visible()
    expect(page.get_by_role("option", name="Amy & Team")).to_have_count(0)
    page.get_by_role("option", name="Ben Santos — Account #2").click()
    expect(combo).to_have_value("Ben Santos — Account #2")
    expect(page.locator("#student")).to_have_value("2")
    expect(combo).to_have_attribute("aria-expanded", "false")
    assert page.evaluate("events") == ["input:2", "change:2"]
    assert page.evaluate("Object.fromEntries(new FormData(document.querySelector('#sample')))") == {"student": "2", "program": "it"}
    assert "student-help" in combo.get_attribute("aria-describedby")
    page.get_by_role("button", name="Save selection").click()
    assert page.evaluate("submits") == 1
    expect(page.locator("#plain")).to_be_visible()
    expect(page.locator("#multiple")).to_be_visible()


def test_keyboard_search_empty_state_and_dismissal(dropdown_page):
    page = dropdown_page
    combo = page.get_by_role("combobox", name="Program", exact=True)
    combo.focus()
    combo.press("ArrowDown")
    combo.press("ArrowDown")  # Skip disabled option.
    combo.press("Enter")
    expect(page.locator("#program")).to_have_value("cs")
    combo.press("ArrowUp")
    combo.press("End")
    combo.press("Enter")
    expect(page.locator("#program")).to_have_value("is")
    combo.press("c")
    combo.press("Enter")
    expect(page.locator("#program")).to_have_value("cs")
    student = page.get_by_role("combobox", name="Student account", exact=True)
    student.click()
    expect(page.get_by_role("group", name="Verified students")).to_be_visible()
    expect(page.get_by_role("option", name="Dana")).to_have_attribute("aria-disabled", "true")
    expect(page.get_by_role("option", name="Hidden student")).to_have_count(0)
    student.fill("nobody matches")
    expect(page.get_by_text("No matching options.")).to_be_visible()
    student.press("Enter")
    assert page.evaluate("submits") == 0
    student.press("Escape")
    expect(student).to_have_value("Choose a student")
    student.click()
    combo.focus()
    combo.click()
    expect(page.locator(":popover-open")).to_have_count(1)
    combo.press("Tab")
    expect(page.locator(":popover-open")).to_have_count(0)
    student.click()
    page.mouse.click(5, 5)
    expect(page.locator(":popover-open")).to_have_count(0)


def test_required_validation_focus_and_form_reset(dropdown_page):
    page = dropdown_page
    combo = page.get_by_role("combobox", name="Student account", exact=True)
    page.get_by_role("button", name="Save selection").click()
    expect(combo).to_be_focused()
    expect(combo).to_have_attribute("aria-invalid", "true")
    expect(page.get_by_role("alert")).to_be_visible()
    assert page.evaluate("submits") == 0
    combo.fill("Amy")
    page.get_by_role("option", name="Amy & Team").click()
    expect(combo).to_have_attribute("aria-invalid", "false")
    page.get_by_role("button", name="Save selection").click()
    assert page.evaluate("submits") == 1
    combo.click()
    page.evaluate("document.querySelector('#sample').reset()")
    expect(combo).to_have_value("Choose a student")
    expect(combo).to_have_attribute("aria-expanded", "false")
    expect(combo).to_have_attribute("aria-invalid", "false")


def test_dynamic_options_disabled_state_and_programmatic_changes(dropdown_page):
    page = dropdown_page
    combo = page.get_by_role("combobox", name="Student account", exact=True)
    page.evaluate("""() => {
        const select = document.querySelector('#student');
        select.append(new Option('<img src=x onerror=alert(1)> New student', '6'));
        select.value = '6'; select.dispatchEvent(new Event('change', {bubbles: true}));
    }""")
    expect(combo).to_have_value("<img src=x onerror=alert(1)> New student")
    combo.click()
    expect(page.locator(".custom-select__list img")).to_have_count(0)
    expect(page.get_by_role("option", name="<img src=x onerror=alert(1)> New student")).to_be_visible()
    page.evaluate("document.querySelector('#student').disabled = true")
    expect(combo).to_be_disabled()
    expect(page.locator(":popover-open")).to_have_count(0)
    page.evaluate("document.querySelector('#student').disabled = false; document.querySelector('#fields').disabled = true")
    expect(combo).to_be_disabled()
    page.evaluate("document.querySelector('#fields').disabled = false")
    expect(combo).to_be_enabled()
    page.evaluate("""() => {
        const select = document.querySelector('#student');
        window.events = [];
        select.value = '2'; CAPRE.syncSelect(select);
    }""")
    expect(combo).to_have_value("Ben Santos — Account #2")
    assert page.evaluate("events") == []
    page.evaluate("document.querySelector('#student').hidden = true")
    expect(combo).to_be_hidden()
    page.evaluate("document.querySelector('#student').hidden = false")
    expect(combo).to_be_visible()


def test_navigation_and_lazy_dialogs_leave_no_detached_dropdowns(dropdown_page):
    page = dropdown_page
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.get_by_role("combobox", name="Student account", exact=True).click()
    page.locator("#next").click()
    expect(page.get_by_role("heading", name="Next page")).to_be_visible()
    expect(page.locator(".custom-select")).to_have_count(2)
    expect(page.locator(":popover-open")).to_have_count(0)
    page.evaluate("""() => {
        const dialog = document.createElement('dialog');
        dialog.id = 'lazy-dialog';
        dialog.innerHTML = '<label for="lazy">Dialog choice</label><select id="lazy"><option>One</option><option>Two</option></select>';
        document.body.append(dialog); dialog.showModal();
    }""")
    combo = page.get_by_role("combobox", name="Dialog choice")
    combo.click()
    expect(page.get_by_role("option", name="Two", exact=True)).to_be_visible()
    page.get_by_role("option", name="Two", exact=True).click()
    expect(page.locator("#lazy")).to_have_value("Two")
    combo.click()
    combo.press("Escape")
    expect(page.locator("#lazy-dialog")).to_be_visible()
    expect(page.locator(":popover-open")).to_have_count(0)
    combo.click()
    page.evaluate("document.querySelector('#lazy-dialog').close()")
    expect(page.locator(":popover-open")).to_have_count(0)
    page.evaluate("document.querySelector('#lazy-dialog').remove()")
    expect(page.locator(".custom-select")).to_have_count(2)
    assert errors == []


@pytest.mark.parametrize("width,dark", [(1322, False), (390, False), (1322, True), (320, True)])
def test_dropdown_theme_and_viewport_bounds(dropdown_page, width, dark):
    page = dropdown_page
    page.set_viewport_size({"width": width, "height": 740})
    page.evaluate("theme => document.documentElement.dataset.theme = theme", "dark" if dark else "light")
    page.get_by_role("combobox", name="Student account", exact=True).click()
    popup = page.get_by_role("listbox", name="Student account", exact=True)
    expect(popup).to_be_visible()
    assert popup.evaluate("""el => {
        const rect = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        return rect.left >= 0 && rect.right <= innerWidth && rect.top >= 0 && rect.bottom <= innerHeight
            && style.backgroundColor === getComputedStyle(document.documentElement).getPropertyValue('--surface-paper').trim().replace(/^#(.+)$/, (_,hex) => `rgb(${hex.match(/../g).map(v=>parseInt(v,16)).join(', ')})`);
    }""")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    if dark:
        assert page.get_by_role("option", name="Amy & Team").evaluate("""el => {
            const luminance = color => color.match(/[\\d.]+/g).slice(0, 3).map(Number).map(v => {
                v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
            }).reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0);
            const style = getComputedStyle(el);
            const background = style.backgroundColor === 'rgba(0, 0, 0, 0)' ? getComputedStyle(el.closest('[role="listbox"]')).backgroundColor : style.backgroundColor;
            const a = luminance(style.color), b = luminance(background);
            return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05) >= 4.5;
        }""")


@pytest.mark.parametrize("width,dark", [(1322, False), (320, False), (390, True)])
def test_compact_filters_submit_once_and_citation_select_stays_local(dropdown_page, width, dark):
    page = dropdown_page
    page.set_viewport_size({"width": width, "height": 800})
    page.add_style_tag(url="http://capre.test/static/css/pages/_archive.css")
    page.evaluate("""dark => {
        document.documentElement.dataset.theme = dark ? 'dark' : 'light';
        document.querySelector('#page-content').innerHTML = `
            <form id="filters" class="filter-form">
                <div class="filter-group"><span>Year:</span><select name="year" class="filter-select"><option value="">All</option><option>2026</option></select></div>
                <div class="filter-group"><span>Specialization:</span><select name="specialization" class="filter-select"></select></div>
            </form>
            <label for="citation">Format</label><select id="citation" class="filter-select"><option value="apa">APA 7</option><option value="bibtex">BibTeX</option></select>`;
        const specialization = document.querySelector('[name="specialization"]');
        for (let i = 0; i < 10; i++) specialization.append(new Option('Specialization number ' + i, String(i)));
        window.filterSubmissions = [];
        document.querySelector('#filters').addEventListener('submit', event => {
            event.preventDefault(); filterSubmissions.push(Object.fromEntries(new FormData(event.target)));
        });
        document.querySelector('#citation').addEventListener('change', event => {window.citationFormat = event.target.value;});
    }""", dark)
    page.add_script_tag(url="http://capre.test/static/js/index.js")
    page.evaluate("CAPRE.initApp(); CAPRE.initApp()")
    year = page.get_by_role("combobox", name="Year:", exact=True)
    expect(year).to_be_visible()
    assert year.evaluate("el => el.getBoundingClientRect().height") == pytest.approx(32, abs=0.5)
    specialization = page.get_by_role("combobox", name="Specialization:", exact=True)
    specialization.fill("number 9")
    assert page.evaluate("filterSubmissions") == []
    popup = page.get_by_role("listbox", name="Specialization:", exact=True)
    assert popup.evaluate("el => el.getBoundingClientRect().right <= innerWidth")
    page.get_by_role("option", name="Specialization number 9", exact=True).click()
    assert page.evaluate("filterSubmissions") == [{"year": "", "specialization": "9"}]
    page.get_by_role("combobox", name="Format", exact=True).click()
    page.get_by_role("option", name="BibTeX", exact=True).click()
    assert page.evaluate("citationFormat") == "bibtex"
    assert page.evaluate("filterSubmissions.length") == 1
    for field in page.locator(".custom-select__input").all():
        assert field.evaluate("el => el.getBoundingClientRect().right <= innerWidth")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_removed_controls_can_be_reinserted_and_long_lists_allow_search(dropdown_page):
    page = dropdown_page
    page.evaluate("window.detachedSelect = document.querySelector('#program'); detachedSelect.closest('.custom-select').remove()")
    expect(page.get_by_role("combobox", name="Program", exact=True)).to_have_count(0)
    page.evaluate("""() => {
        document.querySelector('#fields').append(detachedSelect);
        for (let n = 0; n < 10; n++) detachedSelect.append(new Option('Extra program ' + n, String(n)));
    }""")
    combo = page.get_by_role("combobox", name="Program", exact=True)
    expect(combo).to_be_editable()
    expect(page.locator(".custom-select .custom-select")).to_have_count(0)
    combo.fill("Extra program 9")
    page.get_by_role("option", name="Extra program 9", exact=True).click()
    expect(page.locator("#program")).to_have_value("9")


def test_unsupported_browser_retains_native_dropdown(dropdown_page):
    page = dropdown_page
    page.add_init_script("delete HTMLElement.prototype.showPopover")
    page.reload()
    expect(page.locator("#student")).to_be_visible()
    expect(page.locator(".custom-select")).to_have_count(0)
    page.locator("#student").select_option("2")
    expect(page.locator("#student")).to_have_value("2")


def test_no_javascript_retains_native_dropdown(browser):
    context = browser.new_context(java_script_enabled=False)
    page = context.new_page()
    page.set_content(HTML)
    expect(page.locator("#student")).to_be_visible()
    page.locator("#student").select_option("2")
    expect(page.locator("#student")).to_have_value("2")
    context.close()
