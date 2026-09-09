"""OTP input behavior without sending codes or accessing the database."""
from pathlib import Path

from flask import Flask
from playwright.sync_api import expect
import pytest

from app.routes.forms import VerifyOTPForm


@pytest.fixture
def otp_page(page):
    page.clock.install()
    page.set_content('''<form novalidate>
        <input id="otp" maxlength="6" inputmode="numeric">
        <p class="otp-timer"><span id="countdown" data-expiry-minutes="4">4:00</span></p>
        <button id="submit-btn" type="submit">Verify OTP</button>
    </form>''')
    page.add_script_tag(path=str(Path(__file__).resolve().parents[1] / 'static/js/otp_timer.js'))
    page.evaluate('''() => {
        document.dispatchEvent(new Event('DOMContentLoaded'));
        window.submissions = [];
        document.querySelector('form').addEventListener('submit', event => {
            if (!event.defaultPrevented) window.submissions.push(document.querySelector('#otp').value);
            event.preventDefault();
        });
    }''')
    return page


def test_typing_blocks_letters_and_submits_once_at_six_digits(otp_page):
    field = otp_page.locator('#otp')
    field.press_sequentially('ab0!0c42x0')
    expect(field).to_have_value('00420')
    assert otp_page.evaluate('window.submissions') == []
    field.press_sequentially('1')
    expect(otp_page.locator('#submit-btn')).to_be_disabled()
    field.dispatch_event('input')
    otp_page.locator('form').evaluate('(form) => form.requestSubmit()')
    assert otp_page.evaluate('window.submissions') == ['004201']


def test_paste_strips_letters_spaces_and_extra_digits(otp_page):
    otp_page.locator('#otp').evaluate('''input => {
        const clipboardData = new DataTransfer();
        clipboardData.setData('text', 'Code: 004 20199');
        input.dispatchEvent(new ClipboardEvent('paste', {clipboardData, bubbles: true, cancelable: true}));
    }''')
    expect(otp_page.locator('#otp')).to_have_value('004201')
    assert otp_page.evaluate('window.submissions') == ['004201']


def test_autofill_and_incomplete_manual_submit(otp_page):
    field = otp_page.locator('#otp')
    field.fill('123')
    otp_page.locator('#submit-btn').click()
    assert otp_page.evaluate('window.submissions') == []
    field.fill('004201')
    assert otp_page.evaluate('window.submissions') == ['004201']


def test_expired_code_does_not_auto_submit(otp_page):
    otp_page.clock.run_for(240000)
    otp_page.locator('#otp').fill('004201')
    expect(otp_page.locator('#submit-btn')).to_have_text('OTP Expired')
    assert otp_page.evaluate('window.submissions') == []


@pytest.mark.parametrize('code, valid', [
    ('004201', True), ('12345', False), ('1234567', False),
    ('12345a', False), ('１２３４５６', False), ('12345\n', False),
])
def test_server_requires_six_ascii_digits(code, valid):
    app = Flask(__name__)
    app.config.update(SECRET_KEY='test', WTF_CSRF_ENABLED=False)
    with app.test_request_context(method='POST', data={'otp': code}):
        assert VerifyOTPForm().validate() is valid
