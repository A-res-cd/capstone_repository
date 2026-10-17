"""Pages archive routes and local helpers."""
from . import pages
from flask import render_template, request, session, g, jsonify, current_app, url_for
import psycopg2
from app.db.archive import get_archive_capstones, get_archive_filters
from app.db.requests import get_approved_capstone_ids
from app.db.capstone_requests import get_most_requested_capstones
from app.routes.decorators import login_required


PAGE_SIZE = 12


@pages.route("/archive")
@login_required
def browse():
    search = request.args.get("search", "").strip()
    search_scope = request.args.get("search_scope", "all")
    if search_scope not in {"all", "title", "keyword"}:
        search_scope = "all"
    year = request.args.get("year", "").strip()
    selected_specialization = request.args.get("specialization", type=int)
    selected_program        = request.args.get("program", type=int)
    sort = request.args.get("sort", "newest")
    page = max(1, request.args.get("page", 1, type=int))

    if sort not in {"relevance", "newest", "oldest", "title"}:
        sort = "newest"

    user_id = session.get("user_id")

    projects, total = get_archive_capstones(
        search=search or None,
        search_scope=search_scope,
        year=year   or None,
        page=page,
        page_size=PAGE_SIZE,
        specialization=selected_specialization,
        program=selected_program,
        sort=sort,
    )

    years, programs, specializations = get_archive_filters()
    programs = sorted(programs, key=lambda row: str(row[1] or ""))
    specializations = sorted(specializations, key=lambda row: str(row[1] or ""))
    total_pages = max(1, -(-total // PAGE_SIZE))   # ceiling division

    # sidebar shows the first result by default (or None when list is empty)
    sidebar_project = projects[0] if projects else None

    # Students who already have an approved request for a capstone should
    # see "View Full Manuscript" instead of "View Abstract" / "Request
    # Full Manuscript" — keeps this page in sync with My Requests.
    approved_capstone_ids = []
    current_role = g.user.get("role_name") if g.user else None
    if current_role == "Student":
        if user_id:
            approved_capstone_ids = get_approved_capstone_ids(
                user_id, [project['capstone_id'] for project in projects],
            )

    return render_template(
        "global/explore_archive.html",
        hide_nav=False,
        projects=projects,
        years=years,
        search=search,
        search_scope=search_scope,
        selected_year=year,
        programs=programs,
        specializations=specializations,
        selected_program=selected_program,
        selected_specialization=selected_specialization,
        selected_sort=sort,
        page=page,
        page_size=PAGE_SIZE,
        total=total,
        total_pages=total_pages,
        sidebar_project=sidebar_project,
        approved_capstone_ids=approved_capstone_ids,
    )


@pages.route('/most-requested')
@login_required
def most_requested_page():
    try:
        capstones = get_most_requested_capstones()
    except psycopg2.Error:
        current_app.logger.exception('Could not load most requested capstones')
        capstones = None
    return render_template('global/most_requested_capstones.html',
                           hide_nav=False, most_requested=capstones)


@pages.route('/capstones/most-requested')
@login_required
def most_requested_capstones():
    try:
        limit = int(request.args.get('limit', '5'))
        period = request.args.get('period', 'all')
        capstones = get_most_requested_capstones(limit=limit, period=period)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except psycopg2.Error:
        current_app.logger.exception('Could not load most requested capstones')
        return jsonify({'error': 'Most requested capstones are temporarily unavailable.'}), 503
    for capstone in capstones:
        capstone['detail_url'] = url_for('admin.view_capstone_pdf', capstone_id=capstone['capstone_id'])
    return jsonify({'capstones': capstones, 'limit': limit, 'period': period})
