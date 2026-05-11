from flask import Blueprint, flash, render_template, request, redirect, url_for, session
from flask_mail import Mail, Message
from ..variables.variable import get_nav_links, get_role_meta, resolve_title
from app import mail

main = Blueprint("main", __name__)

@main.app_context_processor
def inject_global_template_vars():
    role = session.get("role_name")

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

@main.route("/")
def home():
    return render_template("index.html", hide_nav=True)