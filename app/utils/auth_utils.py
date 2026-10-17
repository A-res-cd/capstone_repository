
from flask import session, g, request
from app.db.database import db_connect
import psycopg2.extras


def get_current_user(user_id):
    """Get the current logged-in user from the session."""
    if not user_id:
        return None

    conn = db_connect()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT u.user_id, u.user_first_name, u.user_middle_name, u.user_last_name,
               u.role_id, r.role_name, u.locked_until, u.avatar_filename,
               u.account_status, sl.password_id
        FROM "user" u
        JOIN role r ON u.role_id = r.role_id
        JOIN slug sl ON sl.user_id = u.user_id AND sl.is_current = TRUE
        WHERE u.user_id = %s
        LIMIT 1
    """, (user_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    return user


def load_current_user():
    """Load the current user for application requests."""

    if request.endpoint == "static":
        return

    user_id = session.get("user_id")
    if not user_id:
        g.user = None
        return

    g.user = get_current_user(user_id)

    if (g.user is None or g.user['account_status'] != 'active'
            or session.get('password_id') != g.user['password_id']):
        session.clear()
        g.user = None
    else:
        session["role_id"] = g.user["role_id"]
        session["role_name"] = g.user["role_name"]
