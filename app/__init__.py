import os
from flask import Flask
from flask_mail import Mail
from config import Config
from flask_wtf.csrf import CSRFProtect
from apscheduler.schedulers.background import BackgroundScheduler
from flask_debugtoolbar import DebugToolbarExtension

from .auth_utils import load_current_user

mail = Mail()

csrf = CSRFProtect()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    mail.init_app(app)
    csrf.init_app(app)

    app.debug = True
    app.secret_key = app.config["SECRET_KEY"]
    toolbar = DebugToolbarExtension(app)

    app.before_request(load_current_user)

    from .routes import blueprints
    for bp in blueprints:
        app.register_blueprint(bp)

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
