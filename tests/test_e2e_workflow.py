"""
Playwright E2E test for CAPRE core user workflow.
Install:  pip install pytest-playwright && playwright install
Run:      pytest test_e2e_workflow.py --headed  (or without --headed for CI)
"""

import re
from playwright.sync_api import Page, expect

BASE_URL = "http://localhost:5000"


def test_signin_search_logout(page: Page):
    # 1. Open login page
    page.goto(f"{BASE_URL}/signin")
    expect(page).to_have_url(re.compile(r".*signin"))

    # 2. Enter credentials (adjust selectors to match your form field names/ids)
    page.fill("input[name='email']", "student1@example.com")
    page.fill("input[name='password']", "TestPassword123")

    # 3. Submit sign in
    page.click("button[type='submit']")
    page.wait_for_load_state("networkidle")

    # 4. Search the archive
    page.goto(f"{BASE_URL}/archive")
    page.fill("input[name='q']", "capstone")
    page.press("input[name='q']", "Enter")
    page.wait_for_load_state("networkidle")

    # Assert search results rendered (adjust selector to your results container)
    results = page.locator(".archive-result-card")
    expect(results.first).to_be_visible(timeout=5000)

    # 5. Log out
    page.click("a[href*='logout']")
    page.wait_for_load_state("networkidle")
    expect(page).to_have_url(re.compile(r".*(signin|/)$"))


def test_signup_validation(page: Page):
    page.goto(f"{BASE_URL}/signup")

    # Invalid university number should trigger client/server-side validation
    page.fill("input[name='university_number']", "INVALID123")
    page.fill("input[name='email']", "newuser@example.com")
    page.fill("input[name='password']", "TestPassword123")
    page.click("button[type='submit']")

    error = page.locator(".error-message, .invalid-feedback")
    expect(error.first).to_be_visible(timeout=5000)
