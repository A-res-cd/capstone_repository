"""Read current user identity and login lockout state."""
from contextlib import closing

import psycopg2.extras

from app.db.connection import db_connect


def get_current_user(user_id):
    if not user_id:
        return None

    with closing(db_connect()) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT u.user_id, u.user_first_name, u.user_middle_name, u.user_last_name,
                       u.role_id, r.role_name, u.locked_until
                FROM "user" u
                JOIN role r ON u.role_id = r.role_id
                WHERE u.user_id = %s
                LIMIT 1
            """, (user_id,))
            return cur.fetchone()


def get_locked_until(username):
    with closing(db_connect()) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT u.locked_until
                FROM "user" u
                JOIN slug sl ON sl.user_id = u.user_id AND sl.is_current = TRUE
                JOIN kappa k ON k.username_id = sl.username_id
                WHERE LOWER(k.username) = LOWER(%s)
                ORDER BY (k.username = %s) DESC
                LIMIT 1
            """, (username, username))
            row = cur.fetchone()
            return row["locked_until"] if row else None
