"""Review history uses the current academic role permissions."""
from flask import g, render_template, request, session

from . import admin
from app.constants.roles import ROLE_RET_CHAIR, ROLE_CAPSTONE_PROFESSOR, LEGACY_ROLE_NAMES_BY_ID
from app.db.review_history import get_review_history
from app.routes.decorators import role_required


@admin.route('/review-history')
@role_required(ROLE_RET_CHAIR, ROLE_CAPSTONE_PROFESSOR)
def review_history():
    page = max(1, request.args.get('page', 1, type=int))
    recent = request.args.get('view') == 'recent'
    role = g.user.get('role_name') or LEGACY_ROLE_NAMES_BY_ID.get(g.user.get('role_id'))
    reviewer = session['user_id'] if role == ROLE_CAPSTONE_PROFESSOR else None
    rows, total, size = get_review_history(
        page=page, recent=recent, reviewed_by=reviewer,
    )
    return render_template('admin/review_history.html', reviews=rows,
                           total=total, page=page, page_size=size, recent=recent)
