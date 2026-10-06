"""Role boundaries and signup/profile regressions after the full merge."""
from importlib import import_module
from pathlib import Path

from flask import Flask, g, session
import pytest

from app.constants.nav import get_nav_links
from app.routes.forms import SignupForm

ROOT = Path(__file__).resolve().parents[1]
users = import_module('app.routes.admin.users')
history = import_module('app.routes.admin.history')
profile = import_module('app.routes.pages.profile')
faculty = import_module('app.routes.faculty')


@pytest.fixture
def app(monkeypatch):
    app = Flask(__name__, template_folder=str(ROOT / 'app/templates'))
    app.config.update(TESTING=True, SECRET_KEY='merge-fixes', WTF_CSRF_ENABLED=False)
    for module, name in [('app.routes.admin', 'admin'), ('app.routes.pages', 'pages'),
                         ('app.routes.authentication', 'auth'), ('app.routes.faculty', 'faculty')]:
        app.register_blueprint(getattr(import_module(module), name))
    app.add_url_rule('/', endpoint='main.home', view_func=lambda: 'Home')

    @app.before_request
    def current_user():
        g.user = dict(user_id=1, role_name=session.get('role_name'), user_first_name='Test',
                      user_last_name='User', account_status='active')

    @app.context_processor
    def context():
        return dict(hide_header=True, hide_nav=True, csrf_token=lambda: 'test', current_user={})

    monkeypatch.setattr(users, 'get_pending_verifications', lambda: [])
    monkeypatch.setattr(users, 'get_pending_promotion_requests', lambda: [])
    monkeypatch.setattr(users, 'get_all_roles', lambda: [])
    monkeypatch.setattr(users, 'get_users', lambda **kw: ([], 0))
    return app


def login(client, role):
    with client.session_transaction() as state:
        state.update(user_id=1, role_name=role)


@pytest.mark.parametrize('role', ['RET Chair', 'Capstone Professor'])
def test_user_management_role_views(app, monkeypatch, role):
    client = app.test_client()
    login(client, role)
    if role == 'Capstone Professor':
        def forbidden(**kw):
            pytest.fail('Professor must not fetch the user-management list')
        monkeypatch.setattr(users, 'get_users', forbidden)
    response = client.get('/manage_users')
    assert response.status_code == 200
    assert (b'id="tab-users"' in response.data) == (role == 'RET Chair')
    assert (b'id="panel-list-wrap"' in response.data) == (role == 'RET Chair')
    assert b'id="tab-verify"' in response.data
    if role == 'Capstone Professor':
        assert b'id="panel-pending-promotions"' not in response.data
        assert client.post('/manage_users/delete/2').status_code == 302
        assert client.post('/manage_users/update_role/2').status_code == 302


@pytest.mark.parametrize('role', ['RET Chair', 'Capstone Professor'])
def test_verification_details_and_decision_access(app, monkeypatch, role):
    client = app.test_client()
    login(client, role)
    monkeypatch.setattr(users, 'get_verification_details', lambda rid: dict(filename='test.pdf'))
    monkeypatch.setattr(users, 'resolve_cor_file', lambda filename: None)
    monkeypatch.setattr(users, 'get_verification_request_recipient', lambda rid: None)
    decisions = []
    monkeypatch.setattr(users, 'review_verification_request',
                        lambda *args: (decisions.append(args) or True, None))
    assert client.get('/manage_users/verify/2/details').status_code == 200
    assert client.post('/manage_users/verify/2', data={'decision': 'approved'}).status_code == 302
    assert decisions == [(2, 'approved', '', 1)]


def test_ret_chair_can_read_all_review_history(app, monkeypatch):
    client = app.test_client()
    login(client, 'RET Chair')
    calls = []
    monkeypatch.setattr(history, 'get_review_history', lambda **kw: (calls.append(kw) or [], 0, 20))
    assert client.get('/review-history').status_code == 200
    assert calls[0]['reviewed_by'] is None


@pytest.mark.parametrize('view', ['', '?view=recent'])
@pytest.mark.parametrize('request_type,title,label', [
    (None, 'Legacy capstone', 'manuscript'),
    (None, None, 'request'),
    ('verification_student', None, 'verification student'),
])
def test_review_history_renders_missing_request_type(app, monkeypatch, view, request_type, title, label):
    client = app.test_client()
    login(client, 'RET Chair')
    row = dict(request_id=2, request_type=request_type, capstone_title=title,
               request_status='approved', decision_date='2026-10-05',
               requester='Test Student', reviewer='Test Chair', status_reason=None)
    monkeypatch.setattr(history, 'get_review_history', lambda **kw: ([row], 1, 20))
    response = client.get('/review-history' + view)
    assert response.status_code == 200
    assert label.encode() in response.data
    assert (title or label.capitalize()).encode() in response.data


def test_professor_advisory_page_renders_without_avatar(app, monkeypatch):
    client = app.test_client()
    login(client, 'Capstone Professor')
    monkeypatch.setattr(faculty, 'get_user_avatar', lambda uid: None)
    monkeypatch.setattr(faculty, 'get_advisory_roster', lambda uid: [])
    monkeypatch.setattr(faculty, 'get_advisory_groups', lambda uid: [])
    monkeypatch.setattr(faculty, 'get_available_advisory_students', lambda uid: [])
    response = client.get('/faculty/advisory-students')
    assert response.status_code == 200
    assert b'Test User' in response.data


def test_profile_uses_fetched_activity_totals(app, monkeypatch):
    client = app.test_client()
    login(client, 'Student')
    monkeypatch.setattr(profile, 'get_own_profile', lambda uid: dict(user_first_name='Test', user_last_name='User'))
    monkeypatch.setattr(profile, 'get_user_avatar', lambda uid: None)
    monkeypatch.setattr(profile, 'get_user_contacts', lambda uid: [])
    monkeypatch.setattr(profile, 'get_user_authored_capstones', lambda uid: [])
    monkeypatch.setattr(profile, 'get_author_activity_summary', lambda uid: dict(citations=7, views=12, requests=3))
    monkeypatch.setattr(profile, 'get_recent_author_activity', lambda uid: [])
    monkeypatch.setattr(profile, 'get_capstoner_registration', lambda uid: None)
    monkeypatch.setattr(profile, 'get_latest_cor_registration', lambda uid: None)
    contexts = []
    monkeypatch.setattr(profile, 'render_template', lambda name, **kw: (contexts.append(kw) or 'Profile'))
    assert client.get('/profile').status_code == 200
    assert [item['value'] for item in contexts[0]['profile_metrics']] == [0, 7, 12, 3]


def test_navigation_and_signup_markup(app):
    for role in ('RET Chair', 'Capstone Professor'):
        links, _ = get_nav_links(role)
        endpoints = {link['url'] for link in links}
        assert 'admin.audit_logs' not in endpoints
        assert {'admin.manage_users', 'admin.review_history'} <= endpoints
    assert 'faculty.manage_capstone_users' in {link['url'] for link in get_nav_links('Capstone Professor')[0]}
    with app.test_request_context():
        from flask import render_template
        html = render_template('authentication/signup.html', form=SignupForm())
    assert html.count('data-signup-step aria-label=') == 4
    assert html.count('js/signup_steps.js') == 1
    assert html.count('js/signup_cor.js') == 1
    assert 'minlength="8"' in html and '8–12 characters' in html


def test_profile_saves_preferred_contact(app, monkeypatch):
    client = app.test_client()
    login(client, 'Student')
    saved = []
    monkeypatch.setattr(profile, 'save_contact_settings', lambda *args: saved.append(args))
    response = client.post('/user-info/contact', data=dict(
        email='test@example.edu', phone='09171234567', preferred_contact='phone'))
    assert response.status_code == 302
    assert saved == [(1, 'test@example.edu', '+639171234567', 'phone')]


@pytest.mark.parametrize('contact', ['email', 'phone'])
def test_signup_steps_and_terms_in_browser(app, contact):
    from flask import render_template
    from playwright.sync_api import sync_playwright, expect
    with app.test_request_context():
        html = render_template('authentication/signup.html', form=SignupForm())
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.set_content(html)
        page.add_style_tag(path=str(ROOT / 'app/static/css/pages/_auth.css'))
        # The server must render one phase before the wizard script loads.
        expect(page.locator('[data-signup-step]').nth(0)).to_be_visible()
        for index in (1, 2, 3):
            expect(page.locator('[data-signup-step]').nth(index)).to_be_hidden()
        expect(page.locator('#signup-submit')).to_be_hidden()
        expect(page.locator('[data-signup-next]')).to_be_visible()
        page.add_script_tag(path=str(ROOT / 'app/static/js/password_feedback.js'))
        # Local fixture HTML has no server; inject only the signup controls.
        page.add_script_tag(path=str(ROOT / 'app/static/js/signup_steps.js'))
        page.evaluate("document.dispatchEvent(new Event('DOMContentLoaded'))")
        expect(page.locator('[data-signup-step]').nth(0)).to_be_visible()
        expect(page.locator('[data-signup-step]').nth(1)).to_be_hidden()
        page.locator('[data-signup-next]').click()
        expect(page.locator('#signup-step-error')).to_have_text('Upload your COR PDF to continue.')
        page.locator('#cor').set_input_files(dict(name='cor.pdf', mimeType='application/pdf', buffer=b'%PDF-1.4'))
        page.locator('[data-signup-next]').click()
        expect(page.locator('[data-signup-step]').nth(1)).to_be_visible()
        page.locator('#student_no').fill('2026-00001')
        page.locator('#first_name').fill('Test')
        page.locator('#last_name').fill('User')
        page.locator('#username').fill('tester')
        page.locator('#password').fill('TestPass123')
        page.locator('[name="confirm_password"]').fill('TestPass123')
        expect(page.locator('[data-password-rule].is-met')).to_have_count(4)
        expect(page.locator('[data-password-match]')).to_have_text('Passwords match.')
        page.locator('[data-password-toggle="confirm_password"]').click()
        expect(page.locator('[name="confirm_password"]')).to_have_attribute('type', 'text')
        page.locator('[data-password-toggle="confirm_password"]').click()
        expect(page.locator('[name="confirm_password"]')).to_have_attribute('type', 'password')
        page.locator('[data-signup-next]').click()
        expect(page.locator('[data-signup-step]').nth(2)).to_be_visible()
        expect(page.locator('#signup-submit')).to_be_hidden()
        expect(page.locator('#email')).to_be_hidden()
        expect(page.locator('#phone')).to_be_hidden()
        page.locator('[data-signup-next]').click()
        expect(page.locator('#signup-step-error')).to_have_text('Choose email or phone to continue.')
        page.locator('#preferred_contact').select_option('phone')
        expect(page.locator('#phone')).to_be_visible()
        expect(page.locator('#email')).to_be_disabled()
        page.locator('#phone').fill('09171234567')
        page.locator('#preferred_contact').select_option('email')
        expect(page.locator('#email')).to_be_visible()
        expect(page.locator('#phone')).to_be_hidden()
        expect(page.locator('#phone')).to_be_disabled()
        page.locator('#email').fill('test@example.edu')
        page.locator('[data-signup-back]').click()
        expect(page.locator('#username')).to_have_value('tester')
        expect(page.locator('#password')).to_have_value('TestPass123')
        page.locator('[data-step-label]').nth(0).click()
        assert page.locator('#cor').evaluate('input => input.files[0].name') == 'cor.pdf'
        page.locator('[data-step-label]').nth(2).click()
        expect(page.locator('#email')).to_have_value('test@example.edu')
        if contact == 'phone':
            page.locator('#preferred_contact').select_option('phone')
            expect(page.locator('#phone')).to_have_value('09171234567')
        page.locator('[data-signup-next]').click()
        expect(page.locator('[data-signup-step]').nth(3)).to_be_visible()
        expect(page.locator('#signup-submit')).to_be_visible()
        expect(page.locator('#signup-review')).to_contain_text('test@example.edu' if contact == 'email' else '09171234567')
        expect(page.locator('#terms-modal')).to_be_hidden()
        page.locator('#termsLink').click()
        expect(page.locator('#terms-modal')).to_be_visible()
        page.keyboard.press('Escape')
        expect(page.locator('#terms-modal')).to_be_hidden()
        page.locator('#accept_terms').check()
        page.evaluate("() => { window.signupSubmissionCount = 0; HTMLFormElement.prototype.submit = function () { window.signupSubmissionCount++; window.signupSubmission = Object.fromEntries(new FormData(this)); }; }")
        page.locator('#signup-submit').click()
        assert page.evaluate('window.signupSubmission.preferred_contact') == contact
        assert page.evaluate(f'window.signupSubmission.{contact}') == ('test@example.edu' if contact == 'email' else '09171234567')
        assert page.evaluate("'phone' in window.signupSubmission" if contact == 'email' else "'email' in window.signupSubmission") is False
        expect(page.locator('#signup-submit')).to_be_disabled()
        expect(page.locator('#signup-submit')).to_have_text('Creating account...')
        page.evaluate("() => { for (let i = 0; i < 5; i++) document.getElementById('signup-form').dispatchEvent(new Event('submit', {cancelable: true})); }")
        assert page.evaluate('window.signupSubmissionCount') == 1
        page.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}))")
        expect(page.locator('#signup-submit')).to_be_enabled()
        browser.close()


@pytest.mark.parametrize('preference,email,phone,valid', [
    ('email', 'test@example.edu', '', True),
    ('phone', '', '09171234567', True),
    ('email', '', '', False),
    ('phone', '', '', False),
    ('phone', '', 'invalid', False),
    ('', '', '', False),
])
def test_signup_requires_selected_contact(app, preference, email, phone, valid):
    from io import BytesIO
    from werkzeug.datastructures import MultiDict, FileStorage
    with app.test_request_context():
        form = SignupForm(MultiDict(dict(first_name='Test', last_name='User', username='tester',
            password='TestPass123', confirm_password='TestPass123', accept_terms='y',
            preferred_contact=preference, email=email, phone=phone,
            cor=FileStorage(BytesIO(b'%PDF-1.4'), filename='cor.pdf'))))
        assert form.validate() is valid


def test_password_feedback_in_lazily_loaded_change_password_modal(app):
    from flask import render_template
    from app.routes.forms import ChangePasswordForm
    from playwright.sync_api import sync_playwright, expect
    with app.test_request_context():
        html = render_template('partials/user_information_modal.html',
            profile=dict(user_first_name='Test', user_last_name='User', role_name='Student'),
            avatar=None, contacts=[], contact_by_type={}, contact_labels=[], roles=[],
            promotion_requests=[], has_pending_promotion=False, password_form=ChangePasswordForm())
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.set_content('<main id="modal-host"></main>')
        page.add_script_tag(path=str(ROOT / 'app/static/js/password_feedback.js'))
        page.evaluate("html => { document.getElementById('modal-host').innerHTML = html; document.querySelector('dialog').showModal(); }", html)
        password = page.locator('#new_password')
        password.fill('Aa12345678901')
        expect(password).to_have_value('Aa12345678901')
        expect(page.locator('[data-password-status]')).to_have_text('3 of 4 requirements met.')
        assert password.evaluate('input => input.checkValidity()') is False
        password.fill('TestPass123')
        expect(page.locator('[data-password-status]')).to_have_text('Password meets all requirements.')
        page.locator('#confirm_password').fill('Different1')
        expect(page.locator('[data-password-match]')).to_have_text('Passwords do not match.')
        page.locator('#confirm_password').fill('TestPass123')
        expect(page.locator('[data-password-match]')).to_have_text('Passwords match.')
        password.fill('OtherPass1')
        expect(page.locator('[data-password-match]')).to_have_text('Passwords do not match.')
        browser.close()


@pytest.mark.parametrize('role', ['RET Chair', 'Capstone Professor'])
def test_verification_dialog_in_browser(app, monkeypatch, role):
    from playwright.sync_api import sync_playwright, expect
    client = app.test_client()
    login(client, role)
    monkeypatch.setattr(users, 'get_pending_verifications', lambda: [dict(
        request_id=2, full_name='New Student', role='Student', university_no='2026-1')])
    html = client.get('/manage_users').get_data(as_text=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.set_content(html)
        page.add_style_tag(path=str(ROOT / 'app/static/css/pages/_manage-users.css'))
        page.evaluate("window.fetch = async () => ({ok: true, redirected: false, json: async () => ({full_name: 'New Student', filename: 'cor.pdf'})})")
        page.add_script_tag(path=str(ROOT / 'app/static/js/verification_details.js'))
        expect(page.locator('#verification-dialog')).to_have_count(1)
        if role == 'RET Chair':
            page.locator('#tab-verify').click()
        page.locator('[data-verification-details]').click()
        expect(page.locator('#verification-dialog')).to_be_visible()
        expect(page.locator('[data-verification-approve]')).to_be_enabled()
        expect(page.locator('#verification-rejection-reason')).to_be_visible()
        expect(page.locator('[data-verification-file]')).to_have_count(0)
        assert page.locator('[data-verification-decision-form]').first.evaluate('form => form.checkValidity()') is True
        assert page.locator('#verification-reject-form').evaluate('form => form.checkValidity()') is False
        page.locator('#verification-rejection-reason').fill('Please upload a clearer COR.')
        assert page.locator('#verification-reject-form').evaluate("form => new FormData(form).get('status_reason')") == 'Please upload a clearer COR.'
        assert not errors
        browser.close()


def test_header_and_capstone_status_styles_in_browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.set_content('<a class="header-audit-link">Audit Logs</a><label class="status-checkbox"><input type="checkbox">Presented</label>')
        for stylesheet in ['base/root.css', 'components/_forms.css', 'components/_workflow.css', 'pages/_repository.css']:
            page.add_style_tag(path=str(ROOT / 'app/static/css' / stylesheet))
        assert page.locator('.header-audit-link').evaluate("node => getComputedStyle(node).textDecorationLine") == 'none'
        assert page.locator('.status-checkbox input').evaluate("node => getComputedStyle(node).width") == '15px'
        before = page.locator('.status-checkbox').evaluate("node => getComputedStyle(node).backgroundColor")
        page.locator('.status-checkbox input').check()
        after = page.locator('.status-checkbox').evaluate("node => getComputedStyle(node).backgroundColor")
        assert before != after
        browser.close()
