"""Student-only history; every query is scoped to the authenticated student."""
from datetime import timedelta, timezone
from flask import g, jsonify, render_template, request, session, current_app
from . import pages
from app.constants.roles import ROLE_STUDENT, LEGACY_ROLE_NAMES_BY_ID
from app.db.view_history import get_view_history, record_capstone_view
from app.routes.decorators import role_required


@pages.route('/view-history')
@role_required(ROLE_STUDENT)
def view_history():
    page = max(1, request.args.get('page', 1, type=int))
    page_size = 20
    rows, total = get_view_history(session['user_id'], page, page_size)
    for row in rows:
        row['viewed_local'] = row['viewed_at'].astimezone(timezone(timedelta(hours=8))).strftime('%b %d, %Y %I:%M %p')
    return render_template('global/view_history.html', projects=rows,
                           page=page, page_size=page_size, total=total)


@pages.route('/view-history/<int:capstone_id>', methods=['POST'])
@role_required(ROLE_STUDENT)
def remember_capstone(capstone_id):
    if not record_capstone_view(session['user_id'], capstone_id):
        return jsonify({'success': False}), 404
    return jsonify({'success': True})


@pages.after_app_request
def remember_opened_manuscript(response):
    if (request.method == 'GET' and response.status_code == 200
            and request.endpoint in ('admin.view_capstone_pdf', 'pages.view_approved_manuscript')):
        user = getattr(g, 'user', None) or {}
        role = user.get('role_name') or LEGACY_ROLE_NAMES_BY_ID.get(user.get('role_id'))
        if role == ROLE_STUDENT and session.get('user_id'):
            try:
                record_capstone_view(session['user_id'], request.view_args['capstone_id'])
            except Exception:
                current_app.logger.exception('Viewing history unavailable')
    return response
