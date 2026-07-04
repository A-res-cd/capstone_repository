from flask import Flask
from flask_pymongo import PyMongo
from config import Config

mongo = PyMongo()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    app.secret_key = app.config["SECRET_KEY"]

    mongo.init_app(app)

    from .routes import main
    app.register_blueprint(main)

    return app