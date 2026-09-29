import os
import logging
from flask import Flask, abort, g, render_template, request, session, url_for
from flask_mail import Mail
from config import Config
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_debugtoolbar import DebugToolbarExtension

from .utils.auth_utils import load_current_user
from .utils.navigation import LAST_PAGE_SESSION_KEY, last_page_url
from .utils.observability import finish_request_observation, start_request_observation

mail = Mail()

csrf = CSRFProtect()
logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config["MAINTENANCE_BACKUP_ROOT"] = os.environ.get("MAINTENANCE_BACKUP_ROOT", os.path.join(app.root_path, "..", "backups", "system"))
    app.config["MAINTENANCE_RESTORE_TEST_DB"] = os.environ.get("MAINTENANCE_RESTORE_TEST_DB")
    app.config["PUBLIC_BASE_URL"] = os.environ.get("PUBLIC_BASE_URL")
    app.config["APP_VERSION"] = os.environ.get("APP_VERSION", "Not configured")
    for name in ('UPLOAD_MANUSCRIPT_FOLDER', 'UPLOAD_REGISTRATION_FOLDER', 'UPLOAD_AVATAR_FOLDER', 'UPLOAD_PROGRESS_FOLDER'):
        app.config[name] = os.environ.get(name, app.config.get(name))

    mail.init_app(app)
    csrf.init_app(app)

    app.secret_key = app.config["SECRET_KEY"]

    debug_enabled = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true", "yes")
    app.debug = debug_enabled

    if debug_enabled:
        app.config.setdefault("DEBUG_TB_INTERCEPT_REDIRECTS", False)
        DebugToolbarExtension(app)

    app.before_request(load_current_user)
    app.before_request(start_request_observation)
    from app.utils.maintenance_gate import maintenance_gate
    app.before_request(maintenance_gate)

    @app.before_request
    def block_public_uploads():
        static_upload_path = f"{app.static_url_path}/uploads/"
        if request.path.startswith(static_upload_path):
            abort(404)

    @app.after_request
    def prevent_protected_page_cache(response):
        if request.path == "/logout" or getattr(request, "endpoint", None) != "static" and request.path != "/":
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://unpkg.com https://fonts.googleapis.com; "
            "font-src 'self' data: https://unpkg.com https://fonts.gstatic.com; "
            "img-src 'self' data: blob:; "
            "connect-src 'self'; "
            "worker-src 'self' blob: https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
            "frame-src 'self' blob:; "
            "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'",
        )
        if (
            request.method == "GET"
            and response.status_code == 200
            and response.mimetype == "text/html"
            and request.endpoint != "static"
        ):
            page_url = request.full_path.removesuffix("?")
            if len(page_url) <= 1024:
                session[LAST_PAGE_SESSION_KEY] = page_url
        return finish_request_observation(response)

    from .routes import blueprints
    for bp in blueprints:
        app.register_blueprint(bp)

    # ── Error pages ──────────────────────────────────────────────
    @app.errorhandler(400)
    def bad_request(e):
        return render_template(
            "errors/400.html", hide_nav=True, hide_header=True,
            back_url=last_page_url(url_for("main.home")),
        ), 400

    @app.errorhandler(CSRFError)
    def csrf_error(e):
        # A stale/missing CSRF token is by far the most common cause of
        # a 400 here (form left open too long, or opened in two tabs) —
        # same page as the generic 400 handler, just a clearer log line.
        logger.info(
            "CSRF validation failed request_id=%s: %s",
            getattr(g, "request_id", "unknown"),
            e.description,
        )
        return render_template(
            "errors/400.html", hide_nav=True, hide_header=True,
            back_url=last_page_url(url_for("main.home")),
        ), 400

    @app.errorhandler(403)
    def forbidden(e):
        return render_template(
            "errors/403.html", hide_nav=True, hide_header=True,
            back_url=last_page_url(url_for("main.home")),
        ), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template(
            "errors/404.html", hide_nav=True, hide_header=True,
            back_url=last_page_url(url_for("main.home")),
        ), 404

    @app.errorhandler(500)
    def internal_error(e):
        logger.error(
            "Unhandled server error request_id=%s: %s",
            getattr(g, "request_id", "unknown"),
            e,
        )
        return render_template(
            "errors/500.html", hide_nav=True, hide_header=True,
            back_url=last_page_url(url_for("main.home")),
        ), 500

    # Scheduled work runs only in scripts/system_worker.py.

    return app
