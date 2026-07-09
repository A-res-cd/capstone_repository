from flask import Blueprint, render_template, request, redirect, url_for, session, g
from app.constants.nav import get_nav_links, get_role_meta, resolve_title

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
            "current_user": {"username": None, "user_id": None},
            "current_path": request.path,
        }

    nav_links, nav_sections = get_nav_links(role)
    role_meta = get_role_meta(role)

    for link in nav_links:
        try:
            link["url"] = url_for(link["url"])
        except Exception:
            link["url"] = "#"

    page_title = resolve_title(nav_sections, nav_links, request.path)

    return {
        "nav_links":    nav_links,
        "nav_sections": nav_sections,
        "role_meta":    role_meta,
        "page_title":   page_title,
        "is_logged_in": True,
        "current_user": {
            "username": session.get("username"),
            "user_id":  session.get("user_id"),
        },
        "current_path": request.path,
    }


@main.route("/")
def home():
    return render_template("index.html", hide_nav=True)
