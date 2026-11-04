"""Pages archive routes and local helpers."""
from . import pages
from flask import render_template, request
from app.db.archive import get_archive_capstones, get_archive_filters
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
    )
