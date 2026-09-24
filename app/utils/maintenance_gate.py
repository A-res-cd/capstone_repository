"""Maintenance availability for website requests and health checks."""
from flask import current_app, g, jsonify, render_template, request
from psycopg2.errors import UndefinedTable

from app.constants.roles import ROLE_ADMIN
from app.db import system


def maintenance_gate():
    if request.endpoint in {'static', 'auth.signin', 'auth.logout', 'main.health_live'}:
        return
    try:
        state = system.settings()
    except Exception as exc:
        current_app.logger.exception('Unable to read maintenance state')
        if request.blueprint == 'system':
            return
        message = 'Service state unavailable. Please try again.'
        if isinstance(exc, UndefinedTable):
            message = 'Database setup is incomplete. Ask the operator to apply pending database migrations and restart the application.'
        if request.path.startswith('/api/') or request.endpoint == 'main.health_ready':
            response = jsonify(error=message)
        else:
            response = render_template('system/service_unavailable.html', notice=message,
                                       hide_nav=True, hide_header=True)
        return response, 503, {'Retry-After': '300', 'Cache-Control': 'no-store'}
    g.maintenance_notice = state['notice'] if state['maintenance_enabled'] else None
    g.maintenance_active = system.maintenance_active(state)
    if getattr(g, 'user', None) and g.user.get('role_name') == ROLE_ADMIN:
        return
    if g.maintenance_active:
        if request.path.startswith('/api/') or request.endpoint == 'main.health_ready':
            response = jsonify(error=state['notice'], maintenance=True)
        else:
            response = render_template('system/maintenance.html', notice=state['notice'], hide_nav=True, hide_header=True)
        return response, 503, {'Retry-After': '300', 'Cache-Control': 'no-store'}
