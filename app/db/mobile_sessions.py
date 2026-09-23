"""Database-backed mobile sessions, shared across server workers."""
from contextlib import closing
import hashlib
import secrets

from psycopg2.extras import RealDictCursor

from app.db.connection import db_connect


ACCESS_SECONDS = 900
REFRESH_SECONDS = 30 * 24 * 60 * 60


def token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _credentials():
    return {
        "access_token": secrets.token_urlsafe(32),
        "refresh_token": secrets.token_urlsafe(32),
        "token_type": "Bearer",
        "expires_in": ACCESS_SECONDS,
    }


def create_session(user_id):
    credentials = _credentials()
    with closing(db_connect()) as conn, conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM mobile_session WHERE refresh_expires_at <= NOW()")
            cur.execute("""
                INSERT INTO mobile_session
                    (user_id, password_id, access_hash, refresh_hash,
                     access_expires_at, refresh_expires_at)
                SELECT u.user_id, sl.password_id, %s, %s,
                       NOW() + %s * INTERVAL '1 second', NOW() + %s * INTERVAL '1 second'
                FROM "user" u JOIN slug sl ON sl.user_id = u.user_id AND sl.is_current = TRUE
                WHERE u.user_id = %s AND u.account_status = 'active'
                LIMIT 1
                RETURNING mobile_session_id
            """, (token_hash(credentials["access_token"]),
                  token_hash(credentials["refresh_token"]), ACCESS_SECONDS, REFRESH_SECONDS, user_id))
            return credentials if cur.fetchone() else None


def refresh_session(token):
    """Atomic rotation: one refresh succeeds; the old pair stops working."""
    credentials = _credentials()
    with closing(db_connect()) as conn, conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE mobile_session ms
                SET access_hash = %s, refresh_hash = %s,
                    access_expires_at = LEAST(NOW() + %s * INTERVAL '1 second', refresh_expires_at)
                FROM "user" u
                WHERE ms.refresh_hash = %s AND ms.refresh_expires_at > NOW()
                  AND u.user_id = ms.user_id AND u.account_status = 'active'
                  AND (u.locked_until IS NULL OR u.locked_until <= NOW())
                  AND EXISTS (SELECT 1 FROM slug sl WHERE sl.user_id = ms.user_id
                              AND sl.password_id = ms.password_id AND sl.is_current = TRUE)
                RETURNING ms.mobile_session_id
            """, (token_hash(credentials["access_token"]),
                  token_hash(credentials["refresh_token"]), ACCESS_SECONDS, token_hash(token)))
            return credentials if cur.fetchone() else None


def authenticate(token):
    with closing(db_connect()) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT u.user_id, u.user_first_name, u.user_middle_name, u.user_last_name,
                       u.role_id, r.role_name
                FROM mobile_session ms
                JOIN "user" u ON u.user_id = ms.user_id
                JOIN role r ON r.role_id = u.role_id
                WHERE ms.access_hash = %s AND ms.access_expires_at > NOW()
                  AND ms.refresh_expires_at > NOW() AND u.account_status = 'active'
                  AND (u.locked_until IS NULL OR u.locked_until <= NOW())
                  AND EXISTS (SELECT 1 FROM slug sl WHERE sl.user_id = ms.user_id
                              AND sl.password_id = ms.password_id AND sl.is_current = TRUE)
            """, (token_hash(token),))
            return cur.fetchone()


def revoke_session(token):
    """Refresh credentials also allow logout after the access token expires."""
    with closing(db_connect()) as conn, conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM mobile_session WHERE refresh_hash = %s RETURNING user_id",
                        (token_hash(token),))
            row = cur.fetchone()
            return row[0] if row else None


def visible_capstone(capstone_id):
    with closing(db_connect()) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM capstone WHERE capstone_id = %s AND is_archived IS NOT TRUE",
                        (capstone_id,))
            return cur.fetchone() is not None
