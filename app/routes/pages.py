from flask import Blueprint, render_template, request, flash, session, redirect, url_for, jsonify
from app.db.database import (
get_archive_capstones, get_archive_years, request_fullview, get_user_requests, get_capstone_details, 
cancel_manuscript_request, add_citations, get_capstone_authors
)

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

@pages.route("/request_manuscript/<int:capstone_id>", methods=['POST'])
def request_manuscript(capstone_id):
    user_id = session.get("user_id")
    if not user_id:
        flash("You must be logged in to request a manuscript", "warning")
        return redirect(url_for("auth.signin"))
    
    reason = request.form.get("request_reason", "").strip()
    if not reason:
        flash("Please give a reason for your request", "danger")
        return redirect(url_for("pages.manuscript_request_page", capstone_id=capstone_id))
    
    ok, err = request_fullview(user_id, capstone_id, reason)
    flash("request submitted successfully" 
          if ok else f"Error: {err}","success" if ok else "danger") 
    return redirect(url_for("pages.manuscript_request_page", capstone_id=capstone_id))


@pages.route("/requests/<int:capstone_id>", methods=["GET"])
def manuscript_request_page(capstone_id):
    user_id = session.get("user_id")
    
    if not user_id:
        flash("you must log in", "warning")
        return redirect(url_for("auth.signin"))
    
    capstone = get_capstone_details(capstone_id)
    if not capstone:
        flash("capstone not found", "danger")
        return redirect(url_for("pages.browse"))
    
    user_requests = get_user_requests(user_id)
    return render_template("global/manuscript_request.html", capstone = capstone, user_requests = user_requests, hide_nav = False, )

@pages.route("/manuscript/view/<int:capstone_id>")
def view_approved_manuscript(capstone_id):
    user_id = session.get("user_id")
    if not user_id:
        flash("You must be logged in to view this manuscript.", "warning")
        return redirect(url_for("auth.signin"))

    # Confirm this user actually has an approved request for this capstone
    # before letting them view it — otherwise this would just be a second
    # admin-only route under a different name. See BUGS.md #1.
    user_requests = get_user_requests(user_id)
    has_access = any(
        r["capstone_id"] == capstone_id and r["request_status"] == "approved"
        for r in user_requests
    )
    if not has_access:
        flash("You don't have an approved request for this manuscript.", "danger")
        return redirect(url_for("pages.browse"))

    capstone = get_capstone_details(capstone_id)
    if not capstone:
        flash("Capstone not found.", "danger")
        return redirect(url_for("pages.browse"))

    return render_template("admin/view_capstone.html", capstone=capstone, max_pages=None)


@pages.route("/cancel_request/<int:request_id>", methods=["POST"])
def cancel_request(request_id):
    user_id = session.get("user_id")

    if not user_id:
        flash("you must log in", "warning")
        return redirect(url_for("auth.signin"))
    
    ok, err = cancel_manuscript_request(request_id, user_id)

    flash("request cancelled" 
          if ok else f"Error: {err}","success" if ok else "danger") 
    return redirect(request.referrer or url_for("pages.browse"))

@pages.route("/cite/<int:capstone_id>", methods=["POST"])
def cite_capstone(capstone_id):
    user_id =session.get("user_id")
    if not user_id:
        return jsonify({"error": "You must be logged in to cite this capstone"}), 401

    capstone = get_capstone_details(capstone_id)
    if not capstone:
        return jsonify({"error": "capstone not found"}), 404
    
    authors = get_capstone_authors(capstone_id)

    author_parts = []

    for a in authors:
        last = a["aut_last_name"]
        first_initial = a["aut_first_name"][0] + "." if a ["aut_first_name"] else ""
        middle_intitial = a["aut_middle_name"][0] + "." if a ["aut_middle_name"] else ""
        if middle_intitial:
            author_parts.append(f"{last}, {first_initial} {middle_intitial}")
        else:
            author_parts.append(f"{last}, {first_initial}")

    if len(author_parts) == 0:
        author_str = "Unknown Author"
    elif len(author_parts) == 1:
        author_str = author_parts[0]
    else:
        author_str = ", ".join(author_parts[:-1]) + ", &" + author_parts[-1]

    citation = (
        f"{author_str} ({capstone['capstone_year']}). "
        f"{capstone['capstone_title']} "
        f"[Unpublished capstone project]. "
        f"{capstone['program_name']}."
    )
    ok, err = add_citations(capstone_id)
    if not ok:
        return jsonify({"error": err}), 500
    
    update = get_capstone_details(capstone_id)
                        
    return jsonify({"citation": citation, "citation_count": update["citation_count"]})
