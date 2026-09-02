from functools import wraps
from flask import session, g, redirect, url_for, flash

from app.db.requests import get_user_requests
from app.utils.navigation import last_page_url


FULL_MANUSCRIPT_ROLES = {"Admin", "Faculty", "Capstone Professor"}


def login_required(f):
    """Redirect to signin if user is not logged in."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("You must be logged in to access that page.", "warning")
            return redirect(url_for("auth.signin"))
        return f(*args, **kwargs)
    return decorated_function


def role_required(*allowed_roles):
    """Check if user has one of the allowed roles."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if "user_id" not in session:
                flash("You must be logged in.", "warning")
                return redirect(url_for("auth.signin"))

            user_role = None
            if getattr(g, 'user', None):
                user_role = g.user.get("role_id")
            if user_role not in allowed_roles:
                flash("You don't have permission to access that page.", "danger")
                return redirect(last_page_url(url_for("main.home"), avoid_current=True))

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def can_view_full_manuscript(capstone_id, user_id=None):
    role_name = g.user.get("role_name") if getattr(g, "user", None) else session.get("role_name")
    if role_name in FULL_MANUSCRIPT_ROLES:
        return True

    user_id = user_id or session.get("user_id")
    if not user_id:
        return False

    return any(
        r["capstone_id"] == capstone_id and r["request_status"] == "approved"
        for r in get_user_requests(user_id)
    )
