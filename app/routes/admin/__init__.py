"""Register admin features on the shared admin blueprint."""
from flask import Blueprint

admin = Blueprint("admin", __name__)

# Create the blueprint before importing modules that register its routes.
from . import audit
from . import diagnostics
from . import analytics
from . import reports
from . import users
from . import requests
from . import repository
from . import manuscripts
from . import archive
