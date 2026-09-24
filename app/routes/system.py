"""System Administrator console; academic authority belongs to RET Chair."""
from datetime import datetime, timedelta, timezone
import json

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, session, url_for
from itsdangerous import BadSignature, URLSafeTimedSerializer
from werkzeug.exceptions import HTTPException

from app.constants.roles import ROLE_ADMIN
from app.db import system as db
from app.db.auth import sign_in
from app.db.migration_runner import migration_status
from app.services import system_maintenance as service


system = Blueprint('system', __name__, url_prefix='/system')
PAGES = {
    'overview': ('System Overview', 'Review service status and follow alerts to the affected maintenance page.'),
    'diagnostics': ('Diagnostics', 'Run service checks and review their last measured results.'),
    'database': ('Database Health', 'Inspect database capacity, connections, and deployment migration status.'),
    'storage': ('Storage Maintenance', 'Inspect private file storage and preview eligible orphan cleanup.'),
    'backups': ('Backups & Recovery', 'Create and verify database/file bundles; test recovery in a separate database.'),
    'jobs': ('Scheduled Jobs', 'Inspect queued work, worker activity, and completed or failed operations.'),
    'logs': ('Errors & Logs', 'Search sanitized request failures by severity, time, and request ID.'),
    'security': ('Account Security', 'Suspend compromised accounts, clear lockouts, and revoke sessions.'),
    'maintenance': ('Maintenance Mode', 'Schedule downtime and publish a service notice to website users.'),
    'configuration': ('System Configuration', 'Review deployment readiness and configure backup scheduling and retention.'),
    'history': ('Maintenance History', 'Review who changed the system, why, and the resulting operation.'),
}


@system.app_template_filter('split_filename')
def split_filename(value):
    return value.replace('\\', '/').rsplit('/', 1)[-1]


@system.before_request
def administrator_only():
    if not getattr(g, 'user', None):
        return redirect(url_for('auth.signin'))
    if g.user.get('role_name') != ROLE_ADMIN:
        abort(403)


def signer():
    return URLSafeTimedSerializer(current_app.secret_key, salt='maintenance-cleanup')


def _reason():
    reason = request.form.get('reason', '').strip()
    if not 5 <= len(reason) <= 500:
        raise ValueError('Enter a reason between 5 and 500 characters.')
    return reason


def _reauthenticate():
    user, error = sign_in(session.get('username', ''), request.form.get('password', ''), request.remote_addr)
    if not user or user['user_id'] != g.user['user_id'] or user['role_name'] != ROLE_ADMIN:
        raise ValueError(error or 'Confirm your current password.')


def _date(value):
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc) if value else None


def page(page_name):
    state = db.settings()
    rows = db.jobs()
    data = {'state': state, 'jobs': rows, 'active': db.maintenance_active(state),
            'worker_healthy': bool(state['worker_seen_at'] and state['worker_seen_at'] > datetime.now(timezone.utc) - timedelta(minutes=2))}
    if page_name in {'overview', 'diagnostics'}:
        data['diagnostic'] = next((row for row in rows if row['kind'] == 'diagnostics' and row['status'] == 'succeeded'), None)
    if page_name == 'database':
        data['database'] = db.database_health()
        data['migrations'] = migration_status()
    if page_name == 'storage':
        inventory, digest = service.cleanup_preview()
        data['storage'] = inventory
        data['cleanup_token'] = signer().dumps({'digest': digest, 'actor': g.user['user_id']})
    if page_name in {'overview', 'backups'}:
        data['backups'] = service.list_backups()
    if page_name == 'security':
        data['accounts'] = db.security_accounts(request.args.get('q', '')[:100])
    if page_name in {'logs', 'history'}:
        try:
            number = int(request.args.get('page', '1'))
            if number < 1 or number > 100000:
                raise ValueError()
            start, end = _date(request.args.get('start', '')), _date(request.args.get('end', ''))
        except ValueError:
            abort(400, description='Use valid dates and page number.')
        data['events'] = db.events(category='request' if page_name == 'logs' else None,
            severity=request.args.get('severity') or None, request_id=request.args.get('request_id', '')[:50] or None,
            page=number, start=start, end=end)
        data['number'] = number
    if page_name == 'configuration':
        data['configuration'] = {key: current_app.config.get(key) for key in (
            'APP_VERSION', 'DEBUG', 'TESTING', 'SESSION_COOKIE_SECURE', 'SESSION_COOKIE_HTTPONLY',
            'SESSION_COOKIE_SAMESITE', 'MAX_CONTENT_LENGTH', 'UPLOAD_ORPHAN_RETENTION_DAYS')}
        data['configuration']['Restore-test database configured'] = bool(current_app.config.get('MAINTENANCE_RESTORE_TEST_DB'))
    return render_template('system/console.html', current_page=page_name, title=PAGES[page_name][0],
                           description=PAGES[page_name][1], **data)


for name in PAGES:
    system.add_url_rule('/' if name == 'overview' else '/' + name,
                        endpoint=name, view_func=page, defaults={'page_name': name})


@system.post('/jobs')
def queue_job():
    try:
        kind, payload = request.form.get('kind'), {}
        reason = _reason()
        if kind == 'recovery_email':
            raise ValueError('Use Account Security to initiate recovery for a selected account.')
        if kind in {'cleanup', 'restore_test', 'archive_purge'}:
            _reauthenticate()
        if kind == 'cleanup':
            approved = signer().loads(request.form.get('preview', ''), max_age=600)
            if approved['actor'] != g.user['user_id'] or request.form.get('confirm') != 'CLEANUP':
                raise ValueError('Confirm the displayed cleanup preview by typing CLEANUP.')
            payload = {'digest': approved['digest']}
        elif kind in {'verify_backup', 'restore_test'}:
            backup_id = request.form.get('backup_id', '')
            service.bundle_path(backup_id)
            payload = {'backup_id': backup_id}
        elif kind == 'archive_purge':
            raise ValueError('Archive retention runs automatically. RET Chair controls academic deletion decisions.')
        job_id = db.enqueue(kind, g.user['user_id'], reason, payload)
        flash(f'Job {job_id} queued. The maintenance worker will process it.', 'success')
    except (ValueError, BadSignature, KeyError) as exc:
        flash(str(exc) if isinstance(exc, ValueError) else 'Cleanup preview expired. Load a fresh preview.', 'danger')
    return redirect(url_for('system.jobs'))


@system.post('/jobs/<int:job_id>/retry')
def retry_job(job_id):
    original = db.job(job_id)
    if not original or original['status'] != 'failed':
        abort(404)
    try:
        if original['kind'] in {'cleanup', 'archive_purge'}:
            raise ValueError('Create a fresh cleanup preview or wait for the next retention run.')
        if original['kind'] == 'restore_test':
            _reauthenticate()
        db.enqueue(original['kind'], g.user['user_id'], _reason(), original['payload'])
        flash('Retry queued.', 'success')
    except ValueError as exc:
        flash(str(exc), 'danger')
    return redirect(url_for('system.jobs'))


@system.post('/maintenance')
def update_maintenance():
    try:
        reason = _reason()
        _reauthenticate()
        enabled = request.form.get('enabled') == 'yes'
        start, end = _date(request.form.get('start')), _date(request.form.get('end'))
        notice = request.form.get('notice', '').strip()
        if not notice or len(notice) > 500 or end and end <= (start or datetime.now(timezone.utc)):
            raise ValueError('Enter a notice and an end time later than the start time.')
        if not enabled and not all(check['status'] == 'healthy' for check in service.diagnostics()['checks'][:2]):
            raise ValueError('Database and private storage checks must pass before ending maintenance.')
        db.save_settings(g.user['user_id'], reason, enabled=enabled, start=start, end=end, notice=notice)
        flash('Maintenance schedule updated.', 'success')
    except ValueError as exc:
        flash(str(exc), 'danger')
    return redirect(url_for('system.maintenance'))


@system.post('/configuration')
def update_configuration():
    try:
        interval, keep = int(request.form.get('interval', '')), int(request.form.get('keep', ''))
        if not 1 <= interval <= 720 or not 2 <= keep <= 365:
            raise ValueError('Backup interval must be 1–720 hours; retention must be 2–365 bundles.')
        db.save_settings(g.user['user_id'], _reason(), interval=interval, keep=keep)
        flash('Backup settings updated.', 'success')
    except ValueError as exc:
        flash(str(exc), 'danger')
    return redirect(url_for('system.configuration'))


@system.post('/security/<int:user_id>')
def account_action(user_id):
    try:
        reason = _reason()
        _reauthenticate()
        if request.form.get('action') == 'recovery':
            if not db.recovery_recipient(user_id):
                raise ValueError('No eligible primary email contact was found.')
            db.enqueue('recovery_email', g.user['user_id'], reason, {'user_id': user_id})
        else:
            db.secure_account(g.user['user_id'], user_id, request.form.get('action'), reason)
        flash('Account security action completed.', 'success')
    except ValueError as exc:
        flash(str(exc), 'danger')
    return redirect(url_for('system.security'))


@system.get('/logs/export')
def export_logs():
    rows = db.events(category='request', request_id=request.args.get('request_id') or None)
    db.record_event('diagnostic_report_exported', actor=g.user['user_id'], details={'rows': len(rows)})
    response = current_app.response_class(json.dumps(rows, default=str, indent=2), mimetype='application/json')
    response.headers['Content-Disposition'] = 'attachment; filename="diagnostic-report.json"'
    response.headers['Cache-Control'] = 'no-store'
    return response


@system.errorhandler(Exception)
def console_error(error):
    if isinstance(error, HTTPException):
        return error
    current_app.logger.exception('System console request failed')
    return render_template('system/unavailable.html'), 503
