
from flask import session, g, request
from app.db.session_users import get_current_user


def load_current_user():
    """Load the current user for application requests."""

    if request.endpoint == "static":
        return

    user_id = session.get("user_id")
    if not user_id:
        g.user = None
        return

    g.user = get_current_user(user_id)

    if (g.user is None or g.user.get("account_status", "active") != "active"
            or session.get("session_version", 0) != g.user.get("session_version", 0)):
        session.clear()
        g.user = None
    else:
        session["role_id"] = g.user["role_id"]
        session["role_name"] = g.user["role_name"]
