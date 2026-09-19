"""Admin audit routes and local helpers."""
from . import admin
from flask import abort, render_template, request
import logging
from datetime import date, timedelta
from app.db.audit_reader import get_audit_logs
from app.utils.audit_summary import ACTIONS, CATEGORIES
from app.routes.decorators import role_required


logger = logging.getLogger(__name__)


@admin.route('/audit-logs')
@role_required(3)
def audit_logs():
    filters = {key: request.args.get(key, '').strip() for key in ('q', 'category', 'action', 'start', 'end')}
    try:
        page = int(request.args.get('page', '1'))
        if page < 1 or len(filters['q']) > 100:
            raise ValueError
        if filters['category'] and filters['category'] not in CATEGORIES:
            raise ValueError
        if filters['action'] and filters['action'] not in ACTIONS:
            raise ValueError
        query = dict(filters)
        start = date.fromisoformat(filters['start']) if filters['start'] else None
        end = date.fromisoformat(filters['end']) if filters['end'] else None
        if start and end and start > end:
            raise ValueError
        query.update(start=start, end=end + timedelta(days=1) if end else None)
    except (ValueError, OverflowError):
        abort(400, description='Use valid audit filters, dates, and a positive page number.')
    try:
        result = get_audit_logs(query, page)
    except Exception:
        logger.exception('Could not load audit logs')
        abort(503, description='Audit logs are temporarily unavailable.')
    return render_template('admin/audit_logs.html', **result, filters=filters,
                           categories=CATEGORIES, actions=ACTIONS, page_title='Audit Logs')
