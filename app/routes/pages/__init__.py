"""Register pages features on the shared pages blueprint."""
from flask import Blueprint

pages = Blueprint("pages", __name__)

# Create the blueprint before importing modules that register its routes.
from . import archive
from . import profile
from . import manuscripts
from . import topics
