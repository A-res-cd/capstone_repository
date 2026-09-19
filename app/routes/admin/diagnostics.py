"""Admin diagnostics routes and local helpers."""
from . import admin
from flask import abort, render_template, request, session, current_app
import os, sys, random, flask
from app.routes.decorators import role_required


DEV_DEBUG_REAL_TOOL_CHANCE = 1


def _dev_debug_enabled():
    """The real panel dumps session data, full config keys, and request
    headers — that's too much to hand to every admin account in
    production. Require an explicit opt-in env var (or actual Flask
    debug mode) on top of the admin role check."""
    return current_app.debug or os.environ.get("ENABLE_DEV_DEBUG", "").lower() in ("1", "true", "yes")


@admin.route("/dev-debug")
@role_required(3)
def dev_debug():
    if not _dev_debug_enabled():
        abort(404)

    if random.random() >= DEV_DEBUG_REAL_TOOL_CHANCE:
        return render_template("admin/dev_debug_troll.html")

    # ── The real tool — admin-only internal debug panel ──
    safe_config_keys = {
        "DEBUG", "TESTING", "MAX_CONTENT_LENGTH",
        "SESSION_COOKIE_HTTPONLY", "SESSION_COOKIE_SAMESITE",
        "SESSION_COOKIE_SECURE",
    }
    config_items = sorted(
        (k, v)
        for k, v in current_app.config.items()
        if k in safe_config_keys and not callable(v)
    )

    session_items = sorted((key, "set") for key in session.keys())

    safe_header_names = {
        "Accept", "Accept-Encoding", "Accept-Language", "Host", "User-Agent",
    }
    request_headers = sorted(
        (key, value)
        for key, value in request.headers.items()
        if key in safe_header_names
    )

    routes = sorted(
        (
            r.endpoint,
            ", ".join(sorted(m for m in r.methods if m not in ("HEAD", "OPTIONS"))),
            str(r),
        )
        for r in current_app.url_map.iter_rules()
    )

    return render_template(
        "admin/dev_debug_real.html",
        session_items=session_items,
        config_items=config_items,
        routes=routes,
        python_version=sys.version.split()[0],
        flask_version=flask.__version__,
        request_headers=request_headers,
        troll_odds_pct=round((1 - DEV_DEBUG_REAL_TOOL_CHANCE) * 100),
        debug_mode=current_app.debug,
    )
