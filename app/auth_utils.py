
from flask import session, g
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
               u.role_id, r.role_name, u.locked_until
        FROM "user" u
        JOIN role r ON u.role_id = r.role_id
        WHERE u.user_id = %s
        LIMIT 1
    """, (user_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    return user


def load_current_user():
    """Load current user from PostgreSQL every request."""

    user_id = session.get("user_id")
    if not user_id:
        g.user = None
        return

    g.user = get_current_user(user_id)

    if g.user is None:
        session.clear()
    else:
        session["role_id"] = g.user["role_id"]
        session["role_name"] = g.user["role_name"]
