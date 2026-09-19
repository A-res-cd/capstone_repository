"""Register admin features on the existing admin blueprint."""
from flask import Blueprint

admin = Blueprint("admin", __name__)

# Import after blueprint creation so decorators can register their routes.
from . import audit
from . import diagnostics
from . import analytics
from . import users
from . import requests
from . import capstoners
from . import repository
from . import archive
