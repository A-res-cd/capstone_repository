from flask import Blueprint, render_template, request, redirect, url_for, session, g
from app.constants.nav import get_nav_links, get_role_meta, resolve_title, get_breadcrumb

main = Blueprint("main", __name__)


@main.app_context_processor
def inject_global_template_vars():
    role = None
    if getattr(g, 'user', None):
        role = g.user.get("role_name")

    if not role:
        return {
            "nav_links":    [],
            "nav_sections": {},
            "role_meta":    {},
            "page_title":   None,
            "is_logged_in": False,
            "current_user": {
                "username": None, "user_id": None,
                "first_name": "", "last_name": "",
                "display_name": "", "initials": "?",
            },
            "current_path": request.path,
            "breadcrumb": [],
            "nav_collapsed": session.get("nav_collapsed", False),
        }

    nav_links, nav_sections = get_nav_links(role)
    role_meta = get_role_meta(role)

    for link in nav_links:
        try:
            endpoint = link["url"]
            link["_endpoint"] = endpoint
            link["url"] = url_for(endpoint)
        except Exception:
            link["url"] = "#"
            link["_endpoint"] = None

    page_title = resolve_title(nav_sections, nav_links, request.path)
    breadcrumb = get_breadcrumb(nav_links, request.path)

    return {
        "nav_links":    nav_links,
        "nav_sections": nav_sections,
        "role_meta":    role_meta,
        "page_title":   page_title,
        "is_logged_in": True,
        "current_user": {
            "username":     session.get("username"),
            "user_id":      session.get("user_id"),
            "first_name":   session.get("first_name", ""),
            "last_name":    session.get("last_name", ""),
            # Full name for display — falls back to username if name not set
            "display_name": (
                f"{session.get('first_name', '')} {session.get('last_name', '')}".strip()
                or session.get("username", "")
            ),
            # Initials for the avatar circle — up to 2 letters
            "initials": (
                (session.get("first_name", "") or "")[:1].upper() +
                (session.get("last_name",  "") or "")[:1].upper()
            ) or (session.get("username", "?")[:1].upper()),
        },
        "current_path": request.path,
        "breadcrumb": breadcrumb,
        # Flat list of every ancestor endpoint in the breadcrumb chain, so the
        # navbar can mark a root nav link "active" when the current page is a
        # branch nested anywhere underneath it (not just a direct child).
        "breadcrumb_endpoints": [c["endpoint"] for c in breadcrumb if c.get("endpoint")],
        "nav_collapsed": session.get("nav_collapsed", False),
    }


@main.route("/")
def home():
    return render_template("index.html", hide_nav=True, hide_header=True)


@main.route("/toggle-nav", methods=["POST"])
def toggle_nav():
    """Persist the sidebar's collapsed/expanded state in the session so it
    survives page loads and only changes back when the user clicks the
    burger menu again."""
    data = request.get_json(silent=True) or {}
    session["nav_collapsed"] = bool(data.get("collapsed"))
    return "", 204