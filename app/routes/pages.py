from flask import Blueprint, render_template, request
from app.config.mysql import get_archive_capstones, get_archive_years

pages = Blueprint("pages", __name__)

PAGE_SIZE = 12


@pages.route("/archive")
def browse():
    search      = request.args.get("search", "").strip()
    year        = request.args.get("year", "").strip()
    page        = max(1, request.args.get("page", 1, type=int))

    projects, total = get_archive_capstones(
        search=search or None,
        year=year   or None,
        page=page,
        page_size=PAGE_SIZE,
    )

    years       = get_archive_years()
    total_pages = max(1, -(-total // PAGE_SIZE))   # ceiling division

    # sidebar shows the first result by default (or None when list is empty)
    sidebar_project = projects[0] if projects else None

    return render_template(
        "global/explore_archive.html",
        hide_nav=False,
        projects=projects,
        years=years,
        search=search,
        selected_year=year,
        page=page,
        total=total,
        total_pages=total_pages,
        sidebar_project=sidebar_project,
    )


@pages.route("/user-info")
def user_info():
    return render_template("global/user_information.html", hide_nav=False)
