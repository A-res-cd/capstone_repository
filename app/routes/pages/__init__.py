"""Register pages features on the existing pages blueprint."""
from flask import Blueprint, abort, g, request

pages = Blueprint("pages", __name__)


@pages.before_request
def maintenance_role_account_pages_only():
    if getattr(g, 'user', None) and g.user.get('role_name') == 'System Administrator':
        allowed = {'pages.user_info', 'pages.profile_overview', 'pages.user_avatar', 'pages.upload_avatar',
                   'pages.update_user_contact_info', 'pages.update_own_password', 'pages.delete_own_account_route'}
        if request.endpoint not in allowed:
            abort(403)

# Import after blueprint creation so decorators can register their routes.
from . import archive
from . import profile
from . import manuscripts
from . import topics
from . import progress
from . import history
