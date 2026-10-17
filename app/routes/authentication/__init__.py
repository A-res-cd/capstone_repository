"""Register authentication features on the shared auth blueprint."""
from flask import Blueprint

auth = Blueprint("auth", __name__)

from app.utils.auth_rate_limit import throttle_auth
auth.before_request(throttle_auth)

# Create the blueprint before importing modules that register its routes.
from . import sessions
from . import registration
from . import passwords
