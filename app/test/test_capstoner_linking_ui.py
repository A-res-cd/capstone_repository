"""Author-name filtering is only an aid to explicit credit selection."""
import pytest
from playwright.sync_api import expect

from app.test.test_custom_select import dropdown_page


@pytest.fixture
def linking_page(dropdown_page):
    page = dropdown_page
    page.locator('#page-content').evaluate('''el => el.innerHTML = `
        <form data-author-link-form>
            <label for="account">User account</label>
            <select name="user_id" id="account" data-custom-select="search">
                <option value="0">Choose an account</option>
                <option value="1" data-account-name="María L. Cruz">María L. Cruz · Account #1</option>
                <option value="2" data-account-name="Maria Cruz">Maria Cruz · Account #2</option>
                <option value="3" data-account-name="Zoe Stone">Zoe Stone · Account #3</option>
            </select>
            <label for="credit">Unlinked author credit</label>
            <select name="credit" id="credit" data-custom-select="search">
                <option value="">Choose an author</option>
                <option value="1:10" data-author-name="Maria Cruz">Maria Cruz — Orchard Sensors (2026) · Credit #10</option>
                <option value="2:20" data-author-name="Cruz, Maria">Cruz, Maria — Archive Search (2025) · Credit #20</option>
                <option value="3:30" data-author-name="Bob Vega">Bob Vega — Maria Cruz Research (2024) · Credit #30</option>
            </select>
            <p id="author-match-status" role="status"></p>
            <label data-author-filter-controls hidden><input type="checkbox" data-show-all-credits>Show all</label>
            <label><input type="checkbox" name="confirmed">Verified author</label>
            <button type="reset">Reset</button>
        </form>`''')
    page.add_script_tag(url='http://capre.test/static/js/capstoner_linking.js')
    return page


def choose_account(page, name):
    combo = page.get_by_role('combobox', name='User account', exact=True)
    combo.click()
    combo.fill(name)
    page.get_by_role('option', name=name, exact=True).click()


def test_name_filter_keeps_same_name_credits_and_ignores_title_matches(linking_page):
    page = linking_page
    choose_account(page, 'María L. Cruz · Account #1')
    expect(page.locator('#author-match-status')).to_contain_text('2 matching author credits')
    expect(page.locator('#credit')).to_have_value('')
    combo = page.get_by_role('combobox', name='Unlinked author credit', exact=True)
    combo.click()
    expect(page.get_by_role('option', name='Maria Cruz — Orchard Sensors (2026) · Credit #10')).to_be_visible()
    expect(page.get_by_role('option', name='Cruz, Maria — Archive Search (2025) · Credit #20')).to_be_visible()
    expect(page.get_by_role('option', name='Bob Vega — Maria Cruz Research (2024) · Credit #30')).to_have_count(0)
    combo.fill('Archive Search')
    page.get_by_role('option', name='Cruz, Maria — Archive Search (2025) · Credit #20').click()
    expect(page.locator('#credit')).to_have_value('2:20')
    page.get_by_label('Verified author').check()
    choose_account(page, 'Maria Cruz · Account #2')
    expect(page.locator('#credit')).to_have_value('')
    expect(page.get_by_label('Verified author')).not_to_be_checked()


def test_no_match_fallback_reset_and_duplicate_script_initialization(linking_page):
    page = linking_page
    page.add_script_tag(url='http://capre.test/static/js/capstoner_linking.js')
    choose_account(page, 'Zoe Stone · Account #3')
    expect(page.locator('#author-match-status')).to_contain_text('0 matching author credits')
    page.get_by_label('Show all', exact=True).check()
    expect(page.locator('#author-match-status')).to_contain_text('Showing all 3')
    combo = page.get_by_role('combobox', name='Unlinked author credit', exact=True)
    combo.click()
    combo.fill('Orchard')
    page.get_by_role('option', name='Maria Cruz — Orchard Sensors (2026) · Credit #10').click()
    page.get_by_label('Verified author').check()
    page.get_by_label('Show all', exact=True).uncheck()
    expect(page.locator('#credit')).to_have_value('')
    expect(page.get_by_label('Verified author')).not_to_be_checked()
    page.get_by_role('button', name='Reset', exact=True).click()
    expect(page.locator('#author-match-status')).to_contain_text('Choose a user account')
    combo.click()
    expect(page.get_by_role('option', name='Bob Vega — Maria Cruz Research (2024) · Credit #30')).to_be_visible()
