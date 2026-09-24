"""Academic landing page for the RET Chair."""
from flask import render_template

from . import admin
from app.constants.roles import ROLE_RET_CHAIR
from app.routes.decorators import role_required
from app.db.qol import get_admin_pending_nav_counts


@admin.get('/academic-overview')
@role_required(ROLE_RET_CHAIR)
def overview():
    return render_template('admin/overview.html', counts=get_admin_pending_nav_counts())
