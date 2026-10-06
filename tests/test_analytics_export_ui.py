"""Restored export chooser uses the existing report builders and year filter."""
from importlib import import_module
from pathlib import Path
from zipfile import ZipFile
from io import BytesIO

from flask import Flask, render_template
from jinja2 import ChoiceLoader, DictLoader
from playwright.sync_api import expect
import pypdfium2 as pdfium
import pytest

from app.utils.xlsx_export import build_specialization_workbook

ROOT = Path(__file__).resolve().parents[1]
RECORD = dict(id=1, capstone_title='Filtered Project', authors='Test Author', adviser='Test Adviser',
              year=2026, specialization='Web', published=None, utilized=False, presented=True,
              copyright_registered=False)


@pytest.fixture
def analytics_page(page):
    app = Flask(__name__, template_folder=str(ROOT / 'app/templates'))
    app.register_blueprint(import_module('app.routes.admin').admin)
    app.jinja_loader = ChoiceLoader([
        DictLoader({'base.html': '<html><body>{% block content %}{% endblock %}</body></html>'}),
        app.jinja_loader,
    ])
    summary = dict(id=1, name='Web', total=1, published=0, utilized=0, presented=1,
                   copyright_registered=0, total_pct=100)
    data = dict(selected_year=2026, abbreviations=[], total_capstones=1, program_cards=[],
                summary_rows=[summary], summary_totals=summary, trend_years=[2026], trend_series={'Web': [1]})
    for prefix in ['program', 'specialization', 'published', 'utilized', 'presented', 'copyright']:
        data[prefix + '_labels'] = ['Web']
        data[prefix + '_totals'] = [1]
    with app.test_request_context():
        html = render_template('admin/analytics.html', **data)
    page.route('http://capre.test/analytics', lambda route: route.fulfill(body=html, content_type='text/html'))
    page.route('**/static/**', lambda route: route.fulfill(path=ROOT / 'app/static' / route.request.url.split('/static/', 1)[1]))
    specialization = dict(specialization_name='Web', records=[RECORD])
    workbook = build_specialization_workbook([specialization]).getvalue()
    requests = []

    def report(route):
        requests.append(route.request.url)
        if '.xlsx' in route.request.url:
            route.fulfill(body=workbook, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                          headers={'Content-Disposition': 'attachment; filename="filtered-report.xlsx"'})
        elif '/specializations/' in route.request.url:
            route.fulfill(json=dict(success=True, specializations=[specialization]))
        else:
            route.fulfill(json=dict(success=True, specialization='Web', records=[RECORD]))

    page.route('**/analytics/**/report*', report)
    page.goto('http://capre.test/analytics')
    page.add_style_tag(url='http://capre.test/static/css/base/root.css')
    page.add_style_tag(url='http://capre.test/static/css/components/_buttons.css')
    page.add_style_tag(url='http://capre.test/static/css/pages/_analytics.css')
    page.add_script_tag(path=str(ROOT / 'app/static/js/analytics_export.js'))
    page.evaluate("document.dispatchEvent(new Event('DOMContentLoaded'))")
    return page, requests


@pytest.mark.parametrize('scope', ['row', 'all'])
@pytest.mark.parametrize('format', ['xlsx', 'pdf', 'csv'])
def test_choose_and_download_report(analytics_page, scope, format):
    page, requests = analytics_page
    print_button = page.locator(f'[data-print-report][data-report-scope="{scope}"]')
    download_button = page.locator(f'[data-export-report][data-report-scope="{scope}"]')
    assert print_button.inner_text().strip() == ''
    assert download_button.inner_text().strip() == ''
    download_button.click()
    expect(page.locator('#analytics-export-modal')).to_be_visible()
    expect(page.locator('#analytics-export-excel')).to_be_visible()
    expect(page.locator('#analytics-export-submit')).to_be_disabled()
    page.locator(f'[name="export-format"][value="{format}"]').check(force=True)
    with page.expect_download() as downloading:
        page.locator('#analytics-export-submit').click()
    download = downloading.value
    contents = Path(download.path()).read_bytes()
    assert download.suggested_filename.endswith('.' + format)
    assert requests and all('year=2026' in url for url in requests)
    if format == 'csv':
        text = contents.decode('utf-8-sig')
        assert 'Filtered Project' in text and '2026' in text and 'Not reviewed' in text
    elif format == 'pdf':
        with pdfium.PdfDocument(contents) as document:
            text = ''.join(document[i].get_textpage().get_text_range() for i in range(len(document)))
            assert 'Filtered Project' in text and '2026' in text
    else:
        with ZipFile(BytesIO(contents)) as workbook:
            assert 'Filtered Project' in workbook.read('xl/worksheets/sheet1.xml').decode()
    expect(page.locator('#analytics-export-modal')).to_be_hidden()
    expect(download_button).to_be_focused()


def test_export_chooser_closes_with_escape(analytics_page):
    page, _ = analytics_page
    page.locator('[data-export-report]').first.click()
    page.keyboard.press('Escape')
    expect(page.locator('#analytics-export-modal')).to_be_hidden()


def test_print_report_remains_available(analytics_page):
    page, requests = analytics_page
    page.evaluate("""() => {
        window.open = () => {
            const frame = document.createElement('iframe');
            frame.id = 'print-test-frame';
            document.body.appendChild(frame);
            frame.contentWindow.print = () => { window.printCalled = true; };
            frame.contentWindow.focus = () => {};
            return frame.contentWindow;
        };
    }""")
    page.locator('[data-print-report]').first.click()
    page.wait_for_function('window.printCalled === true')
    expect(page.frame_locator('#print-test-frame').locator('body')).to_contain_text('Filtered Project')
    assert requests and 'year=2026' in requests[-1]
