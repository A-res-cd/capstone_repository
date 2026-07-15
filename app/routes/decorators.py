from functools import wraps
from flask import session, g, redirect, url_for, flash


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
                return redirect(url_for("auth.signin"))

            return f(*args, **kwargs)
        return decorated_function
    return decorator
