"""Register authentication features on the shared auth blueprint."""
from flask import Blueprint

auth = Blueprint("auth", __name__)

# Create the blueprint before importing modules that register its routes.
from . import sessions
from . import registration
from . import passwords
