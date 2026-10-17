from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect

from tests.test_original_branch_features import feature_app, pdf_bytes


@pytest.mark.parametrize('width,height', [(1280, 900), (1280, 720), (390, 844)])
def test_signup_scroll_and_live_password_checks(feature_app, page, width, height):
    client = feature_app.test_client()

    def handle(route):
        url = urlsplit(route.request.url)
        if url.netloc != 'signup.test':
            route.abort()
            return
        if url.path == '/signup/extract-cor':
            route.fulfill(json={})
            return
        response = client.get(url.path)
        route.fulfill(status=response.status_code, body=response.data, content_type=response.content_type)

    page.route('**/*', handle)
    page.set_viewport_size({'width': width, 'height': height})
    page.goto('http://signup.test/signup')
    page.evaluate('document.fonts.ready')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    if width > 900:
        sizes = page.locator('#signup-form').evaluate('el => [el.scrollHeight, el.clientHeight]')
        assert sizes[0] <= sizes[1] + 1, sizes
    page.locator('#cor').set_input_files(dict(name='cor.pdf', mimeType='application/pdf', buffer=pdf_bytes()))
    expect(page.locator('#cor')).to_have_attribute('data-extracting', 'false')
    page.locator('[data-signup-next]').click()
    password = page.locator('#password')
    expect(password).to_have_attribute('maxlength', '12')
    password.fill('abc')
    expect(page.locator('[data-rule="lowercase"]')).to_have_attribute('data-valid', 'true')
    expect(page.locator('[data-rule="lowercase"]')).to_have_css('color', 'rgb(30, 132, 73)')
    expect(page.locator('[data-rule="length"]')).to_have_attribute('data-valid', 'false')
    assert page.locator('[data-rule="lowercase"]').evaluate('el => getComputedStyle(el).color') != page.locator('[data-rule="length"]').evaluate('el => getComputedStyle(el).color')
    password.evaluate("el => { el.value = 'Abc1234567890'; el.dispatchEvent(new Event('input', {bubbles: true})); }")
    expect(page.locator('[data-rule="length"]')).to_have_attribute('data-valid', 'false')
    password.fill('Abc123456789')
    expect(page.locator('[data-password-checklist] [data-valid="true"]')).to_have_count(4)
    page.locator('#confirm_password').fill('Abc123456789')
    expect(page.locator('[data-password-match]')).to_have_attribute('data-valid', 'true')
    password.fill('abc')
    expect(page.locator('[data-rule="uppercase"]')).to_have_attribute('data-valid', 'false')
    expect(page.locator('[data-password-match]')).to_have_attribute('data-valid', 'false')
