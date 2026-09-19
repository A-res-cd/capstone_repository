"""Register pages features on the existing pages blueprint."""
from flask import Blueprint

pages = Blueprint("pages", __name__)

# Import after blueprint creation so decorators can register their routes.
from . import archive
from . import profile
from . import manuscripts
from . import topics
