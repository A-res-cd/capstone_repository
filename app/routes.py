from flask import Blueprint, render_template, request, redirect, url_for, session
from .variables.variable import get_nav_links, get_role_meta, resolve_title

main = Blueprint("main", __name__)


@main.app_context_processor
def inject_global_template_vars():
    role = session.get("role", "Admin")

    # 2. Get nav + role meta
    nav_links, nav_sections = get_nav_links(role)
    role_meta = get_role_meta(role)

    # 3. Resolve title automatically
    page_title = resolve_title(nav_sections, nav_links, request.path)

    return {
        "nav_links": nav_links,
        "nav_sections": nav_sections,
        "role_meta": role_meta,
        "page_title": page_title,
    }

# --- Landings & Auth routes ---


@main.route("/")
def home():
    return render_template("index.html", hide_nav=True)


@main.route("/signin")
def signin():
    return render_template("authentication/signin.html", hide_nav=True, hide_header=True)


@main.route('/signup')
def signup():
    return render_template("authentication/signup.html", hide_nav=True, hide_header=True)


@main.route("/logout")
def logout():
    return render_template("index.html", hide_nav=True, hide_header=True)


# --- Admin specific routes ---
@main.route("/analytics")
def admin_analytics():
    return render_template("admin/analytics.html", hide_nav=False)


@main.route("/manage_users")
def admin_manage_users():
    return render_template("admin/manage_users.html", hide_nav=False)


@main.route("/requests")
def admin_requests():
    return render_template("admin/requests.html", hide_nav=False)


@main.route("/add_capstone_record")
def admin_add_capstone_record():
    return render_template("admin/add_capstone_record.html", hide_nav=False)
