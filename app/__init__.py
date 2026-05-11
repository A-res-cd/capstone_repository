from flask import Flask
from flask_mail import Mail
from config import Config

mail = Mail()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    mail.init_app(app)
    
    app.secret_key = app.config["SECRET_KEY"]

    from .routes import blueprints
    for bp in blueprints:
        app.register_blueprint(bp)

    return app