import os
import logging
from flask import Flask, abort, render_template, request, session, url_for
from flask_mail import Mail
from config import Config
from flask_wtf.csrf import CSRFProtect, CSRFError
from apscheduler.schedulers.background import BackgroundScheduler
from flask_debugtoolbar import DebugToolbarExtension

from .auth_utils import load_current_user
from .utils.navigation import LAST_PAGE_SESSION_KEY, last_page_url

mail = Mail()

csrf = CSRFProtect()
logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    mail.init_app(app)
    csrf.init_app(app)

    app.secret_key = app.config["SECRET_KEY"]

    debug_enabled = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true", "yes")
    app.debug = debug_enabled

    if debug_enabled:
        app.config.setdefault("DEBUG_TB_INTERCEPT_REDIRECTS", False)
        DebugToolbarExtension(app)

    app.before_request(load_current_user)

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
        return response

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
        logger.info("CSRF validation failed: %s", e.description)
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
        logger.error("Unhandled server error: %s", e)
        return render_template(
            "errors/500.html", hide_nav=True, hide_header=True,
            back_url=last_page_url(url_for("main.home")),
        ), 500

    # Run once on startup, then every 24h. WERKZEUG_RUN_MAIN check avoids
    # starting the job twice under the Flask dev server's reloader.
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        from datetime import datetime
        from app.db.database import purge_expired_archived_capstones
        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(
            purge_expired_archived_capstones,
            "interval",
            hours=24,
            next_run_time=datetime.now(),
        )
        scheduler.start()

    return app
