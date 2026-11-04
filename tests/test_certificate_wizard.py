"""Exercise the real repository modal with all certification choices."""
from pathlib import Path

from flask import Flask, render_template, session
from jinja2 import ChoiceLoader, DictLoader
import pytest

from app.routes.forms import CreateCapstoneForm


def test_certificate_wizard(tmp_path):
    playwright = pytest.importorskip('playwright.sync_api')
    root = Path(__file__).resolve().parents[1]
    app = Flask(__name__, template_folder=str(root / 'app/templates'))
    app.config.update(SECRET_KEY='test', WTF_CSRF_ENABLED=False)
    app.jinja_env.loader = ChoiceLoader([DictLoader({'base.html': '''<!doctype html>
        <link rel="stylesheet" href="/static/css/base/global.css">
        <link rel="stylesheet" href="/static/css/components/_buttons.css">
        <link rel="stylesheet" href="/static/css/components/_forms.css">
        {% block extra_css %}{% endblock %}<main>{% block content %}{% endblock %}</main>
        {% block extra_js %}{% endblock %}'''}), app.jinja_env.loader])
    app.jinja_env.globals['url_for'] = lambda endpoint, **kwargs: '/static/' + kwargs['filename'] if endpoint == 'static' else '/action'
    app.jinja_env.globals['csrf_token'] = lambda: 'test'
    with app.test_request_context():
        session['role_name'] = 'Admin'
        html = render_template('admin/repository.html', form=CreateCapstoneForm(), capstones=[],
                               programs=[(1, 'BSIT', 'BSIT')], specializations=[(1, 'Database', 'DST')],
                               specialization_rules={'BSIT': ['DST']}, years=[], total_pages=1, page=1)

    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))

        def serve(route):
            path = route.request.url.split('http://capre.test', 1)[-1]
            if path.startswith('/static/'):
                route.fulfill(path=str(root / 'app' / path.lstrip('/')))
            else:
                route.fulfill(body=html, content_type='text/html')

        page.route('http://capre.test/**', serve)
        for utilized, copyright in [(False, False), (True, False), (False, True), (True, True)]:
            page.goto('http://capre.test/')
            page.locator('#btn-open-create').click()
            page.locator('#extract-file-input').set_input_files({'name': 'manuscript.docx', 'mimeType': 'application/octet-stream', 'buffer': b'test'})
            page.locator('#capstone_title').fill('Test capstone')
            page.locator('#capstone_year').fill('2026')
            page.locator('#program_id').select_option('1')
            page.locator('#specialization_id').select_option('1')
            page.locator('#semester').select_option('1st')
            page.locator('#capstone_keywords').fill('testing')
            page.locator('#is_utilized').set_checked(utilized)
            page.locator('#is_copyright_registered').set_checked(copyright)
            assert page.locator('#is_published, #is_presented').count() == 0
            if utilized and copyright:
                page.screenshot(path=str(tmp_path / 'certificate-status.png'))
            page.locator('#btn-step-next').click()
            if utilized or copyright:
                assert page.locator('[data-step="certificates"]').is_visible()
                assert page.locator('[data-step-dot="2"] .form-step-dot__num').inner_text() == '3'
                page.locator('#btn-certificate-next').click()
                assert page.locator('[data-step="certificates"]').is_visible()
                for flag, prefix in [(utilized, 'utilization'), (copyright, 'copyright')]:
                    assert page.locator(f'[data-certificate="{prefix}"]').is_visible() == flag
                    if flag:
                        page.locator('#' + ('copyright_cert_date' if prefix == 'copyright' else 'utilization_date')).fill('2026-11-05')
                        page.locator('#' + ('copyright_cert_file' if prefix == 'copyright' else 'utilization_file')).set_input_files({'name': 'certificate.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-1.4 certificate'})
                if copyright:
                    page.locator('#copyright_cert_num').fill('COPY-1')
                if utilized and copyright:
                    page.screenshot(path=str(tmp_path / 'certificate-details.png'))
                page.locator('#btn-certificate-next').click()
            else:
                assert page.locator('[data-step-dot="certificates"]').is_hidden()
                assert page.locator('[data-step-dot="2"] .form-step-dot__num').inner_text() == '2'
            assert page.locator('[data-step="2"]').is_visible()
            page.locator('#btn-step-back').click()
            assert page.locator('[data-step="certificates"]' if utilized or copyright else '[data-step="1"]').is_visible()
        assert not errors
        browser.close()
