"""PostgreSQL-backed, atomic limits shared by all application workers."""
import hashlib
import logging
from contextlib import closing

from flask import current_app, make_response, render_template, request, session
from app.db.connection import db_connect

logger = logging.getLogger(__name__)
LIMITS = {
    'auth.signin': ((10, 60), (50, 3600)),
    'auth.signup': ((5, 3600),),
    'auth.extract_cor': ((10, 60), (60, 3600)),
    'auth.forgot_password': ((5, 900),),
    'auth.verify_otp_route': ((10, 900),),
    'auth.reset_password_route': ((10, 900),),
    'auth.verify_signup_email': ((5, 900), (20, 3600)),
}

GLOBAL_LIMITS = {
    'auth.signup': (100, 3600), 'auth.extract_cor': (300, 3600),
    'auth.signin': (5000, 3600), 'auth.forgot_password': (200, 3600),
    'auth.verify_signup_email': (200, 3600),
}
ACTION_LIMITS = {
    # Values are (shared action key, user limits, IP limits).
    'pages.request_manuscript': ('manuscript-actions', ((5, 60), (10, 3600)), ((100, 3600),)),
    'pages.cancel_request': ('manuscript-actions', ((5, 60), (10, 3600)), ((100, 3600),)),
    'pages.topic_similarity': ('topic-similarity', ((10, 60), (100, 3600)), ((300, 3600),)),
    'pages.update_picture': ('profile-picture', ((3, 60), (10, 3600)), ((30, 3600),)),
    'pages.update_user_contact_info': ('profile-contact', ((5, 600),), ((30, 600),)),
    'pages.confirm_user_contact': ('profile-contact-confirm', ((10, 900),), ((30, 900),)),
    'pages.update_own_password': ('profile-password', ((5, 900),), ((30, 900),)),
    'pages.delete_own_account_route': ('profile-delete', ((3, 900),), ((15, 900),)),
    'pages.remember_capstone': ('view-history', ((60, 60),), ((300, 60),)),
    'pages.cite_capstone': ('citations', ((30, 60),), ((150, 60),)),
    'main.read_notifications': ('notifications', ((30, 60),), ((150, 60),)),
}
BROWSE_ENDPOINTS = {
    'pages.browse', 'pages.most_requested_capstones', 'pages.most_requested_page', 'pages.view_history',
    'pages.all_requests', 'pages.request_capstone', 'pages.view_approved_manuscript',
    'pages.manuscript_file', 'pages.manuscript_pages', 'pages.manuscript_page_image',
    'pages.own_picture', 'admin.view_capstone_pdf',
}


def consume_limit(endpoint, client_ip, limit, seconds):
    key = hashlib.sha256(f'{endpoint}:{seconds}:{client_ip}'.encode()).hexdigest()
    with closing(db_connect()) as conn, conn.cursor() as cursor:
        cursor.execute("""
            DELETE FROM auth_rate_limit WHERE bucket_key IN (
                SELECT bucket_key FROM auth_rate_limit
                WHERE window_start < CURRENT_TIMESTAMP - INTERVAL '24 hours'
                ORDER BY window_start LIMIT 100
            )
        """)
        cursor.execute("""
            INSERT INTO auth_rate_limit (bucket_key, window_start, attempts)
            VALUES (%s, CURRENT_TIMESTAMP, 1)
            ON CONFLICT (bucket_key) DO UPDATE SET
                attempts = CASE WHEN auth_rate_limit.window_start <= CURRENT_TIMESTAMP - (%s * INTERVAL '1 second')
                                THEN 1 ELSE auth_rate_limit.attempts + 1 END,
                window_start = CASE WHEN auth_rate_limit.window_start <= CURRENT_TIMESTAMP - (%s * INTERVAL '1 second')
                                    THEN CURRENT_TIMESTAMP ELSE auth_rate_limit.window_start END
            RETURNING attempts, GREATEST(1, CEIL(EXTRACT(EPOCH FROM
                window_start + (%s * INTERVAL '1 second') - CURRENT_TIMESTAMP)))::INTEGER
        """, (key, seconds, seconds, seconds))
        attempts, retry_after = cursor.fetchone()
        conn.commit()
    return retry_after if attempts > limit else None


def _limited_response(retry_after):
    message = f'Too many requests. Please try again in {retry_after} seconds.'
    if (request.is_json or request.endpoint in {
            'auth.extract_cor', 'pages.most_requested_capstones', 'pages.topic_similarity',
            'pages.remember_capstone', 'pages.cite_capstone', 'main.read_notifications', 'pages.manuscript_pages'}
            or request.accept_mimetypes.best == 'application/json'):
        response = make_response({'error': message}, 429)
    else:
        response = make_response(render_template('errors/429.html', message=message,
                                                hide_nav=True, hide_header=True), 429)
    response.headers['Retry-After'] = str(retry_after)
    return response


def _enforce(buckets):
    try:
        for key, identity, limit, seconds in buckets:
            retry_after = consume_limit(key, identity, limit, seconds)
            if retry_after:
                return _limited_response(retry_after)
    except Exception:
        logger.exception('Request throttle unavailable')
        return make_response({'error': 'Services are temporarily unavailable. Please try again.'}, 503)


def throttle_auth():
    if request.method != 'POST' or not current_app.config.get('AUTH_RATE_LIMIT_ENABLED', True):
        return
    endpoint = request.endpoint
    ip = request.remote_addr or 'unknown'
    buckets = [(endpoint, ip, limit, seconds) for limit, seconds in LIMITS.get(endpoint, ())]
    if endpoint in GLOBAL_LIMITS:
        limit, seconds = GLOBAL_LIMITS[endpoint]
        buckets.append((endpoint + ':global', 'all', limit, seconds))
    # Recipient limits survive IP changes and bound email harassment.
    if endpoint == 'auth.forgot_password' or (endpoint == 'auth.verify_signup_email' and request.form.get('action') == 'send'):
        email = request.form.get('email', '').strip().lower()[:254]
        if email:
            buckets.append(('email-delivery', email, 3, 3600))
    if endpoint == 'auth.signup':
        email = request.form.get('email', '').strip().lower()[:254]
        if email:
            buckets.append(('signup-email', email, 3, 3600))
    if endpoint == 'auth.signin':
        username = request.form.get('username', '').strip().lower()[:30]
        if username:
            buckets.extend(('signin-username', username, limit, seconds)
                           for limit, seconds in ((30, 900), (100, 3600)))
    return _enforce(buckets)


def throttle_actions():
    if not current_app.config.get('ACTION_RATE_LIMIT_ENABLED', True):
        return
    endpoint = request.endpoint
    ip = request.remote_addr or 'unknown'
    user_id = session.get('user_id')
    buckets = []
    if (request.method == 'POST' or (endpoint == 'pages.cite_capstone' and request.method in ('GET', 'HEAD'))) and endpoint in ACTION_LIMITS:
        key, user_limits, ip_limits = ACTION_LIMITS[endpoint]
        buckets.extend((key + ':ip', ip, limit, seconds) for limit, seconds in ip_limits)
        if user_id:
            buckets.extend((key + ':user', str(user_id), limit, seconds) for limit, seconds in user_limits)
    elif request.method in ('GET', 'HEAD') and endpoint in BROWSE_ENDPOINTS:
        buckets.append(('browse:ip', ip, 600, 60))
        if user_id:
            buckets.append(('browse:user', str(user_id), 120, 60))
    return _enforce(buckets)
