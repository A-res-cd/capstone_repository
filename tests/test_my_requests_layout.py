from datetime import datetime
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect

from app.routes.pages import manuscripts
from tests.test_original_branch_features import feature_app, login


@pytest.mark.parametrize('width', [1920, 1280, 390])
def test_request_cards_fit_long_content(feature_app, page, monkeypatch, width):
    client = feature_app.test_client()
    login(client, 1)
    title = 'Design and Development of a Mobile Scholarship Application System ' * 6
    requests = [dict(request_id=i, capstone_id=i, capstone_title=title,
                     capstone_year=2025, specialization_name='Web Systems Technology',
                     request_date=datetime(2026, 10, 13), decision_date=datetime(2026, 10, 13),
                     request_status=status, request_reason='ResearchReference' * 30,
                     status_reason='ReviewFeedback' * 30)
                for i, status in enumerate(('pending', 'approved', 'rejected'), 1)]
    monkeypatch.setattr(manuscripts, 'get_user_requests', lambda _: requests)
    monkeypatch.setattr(manuscripts, 'get_requestable_capstones', lambda _: [])

    def handle(route):
        url = urlsplit(route.request.url)
        if url.netloc != 'requests.test':
            route.abort()
            return
        response = client.get(url.path)
        route.fulfill(status=response.status_code, body=response.data, content_type=response.content_type)

    page.route('**/*', handle)
    page.set_viewport_size({'width': width, 'height': 1000})
    page.goto('http://requests.test/my-requests')
    for status, action in (('pending', 'Cancel'), ('approved', 'View'), ('rejected', 'Resubmit')):
        page.locator(f'.mr-tab[data-target="mr-table-{status}"]').click()
        panel = page.locator(f'#mr-table-{status}')
        expect(panel.locator('.record-card__title')).to_have_text(title.strip())
        expect(panel.get_by_text(action, exact=True)).to_be_visible()
        assert page.locator('#page-content').evaluate('el => el.scrollWidth <= el.clientWidth + 1')
        for selector in ('.record-card', '.record-card__body', '.record-card__title', '.request-timeline'):
            assert panel.locator(selector).evaluate('el => el.scrollWidth <= el.clientWidth + 1'), selector
        assert panel.locator('.record-card__actions').evaluate('el => el.getBoundingClientRect().right <= innerWidth')
