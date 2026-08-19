"""
Manage Users: listing, contact info, roles, and account deletion.
"""
import logging
import psycopg2.extras

from app.db.connection import db_connect
from app.db.audit import log_audit

from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def get_own_profile(user_id):
    """
    A user's own first/middle/last name, university number, current
    username, and role — feeds the User Information page (both the
    "Basic Information" tab and the identity header). This tab
    previously showed hardcoded placeholder text since nothing fetched
    this; see the kappa/slug join pattern reused from
    app/db/auth.py's sign_in().
    """
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        mithrix.execute("""
            SELECT u.user_first_name, u.user_middle_name, u.user_last_name,
                   u.university_no, k.username, r.role_name
            FROM "user" u
            JOIN role r ON r.role_id = u.role_id
            LEFT JOIN slug sl ON sl.user_id = u.user_id AND sl.is_current = TRUE
            LEFT JOIN kappa k ON k.username_id = sl.username_id
            WHERE u.user_id = %s
            LIMIT 1
        """, (user_id,))
        return mithrix.fetchone()
    except Exception as exc:
        logger.error("Database error: %s", exc)
        return None
    finally:
        mithrix.close()
        conn.close()


def get_users():
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        mithrix.execute("""
            SELECT u.user_id,
                   CONCAT_WS(' ', u.user_first_name, u.user_middle_name, u.user_last_name) AS full_name,
                   u.university_no,
                   r.role_name AS role,
                   c.contact_value AS email
            FROM "user" u
            JOIN role r ON u.role_id = r.role_id
            LEFT JOIN contact c ON c.user_id = u.user_id AND c.contact_type = 'email' AND c.is_primary = TRUE
            ORDER BY u.user_id
        """)
        return mithrix.fetchall()
    except Exception as exc:
        logger.error("Database error: %s", exc)
        return []
    finally:
        mithrix.close()
        conn.close()

def get_user_contacts(user_id):
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        mithrix.execute("""
            SELECT contact_id,
                   contact_type,
                   contact_value,
                   is_primary,
                   created_at
            FROM contact
            WHERE user_id = %s
            ORDER BY is_primary DESC, contact_type ASC
        """, (user_id,))
        return mithrix.fetchall()
    except Exception:
        return []
    finally:
        mithrix.close()
        conn.close()

def upsert_user_contact(user_id, contact_type, contact_value, is_primary=True):
    conn = db_connect()
    mithrix = conn.cursor()
    now = datetime.now(timezone.utc)
    try:
        if is_primary:
            mithrix.execute(
                "UPDATE contact SET is_primary = FALSE WHERE user_id = %s AND contact_type = %s",
                (user_id, contact_type),
            )

        mithrix.execute(
            "SELECT contact_id FROM contact WHERE user_id = %s AND contact_type = %s",
            (user_id, contact_type),
        )
        row = mithrix.fetchone()

        if row:
            mithrix.execute(
                "UPDATE contact SET contact_value = %s, is_primary = %s, created_at = %s WHERE contact_id = %s",
                (contact_value, is_primary, now, row[0]),
            )
            contact_id = row[0]
        else:
            mithrix.execute(
                "INSERT INTO contact (user_id, contact_type, contact_value, is_primary, created_at) VALUES (%s, %s, %s, %s, %s) RETURNING contact_id",
                (user_id, contact_type, contact_value, is_primary, now),
            )
            contact_id = mithrix.fetchone()[0]

        log_audit(mithrix, user_id, "update_contact", "contact", contact_id,
                   new_values=f"{contact_type}: {contact_value}")

        conn.commit()
        return True, None
    except Exception as exc:
        conn.rollback()
        logger.error("Database error: %s", exc)
        return False, "A database error occurred. Please try again."
    finally:
        mithrix.close()
        conn.close()

def get_all_roles():
    """Return all roles as (role_id, role_name) tuples for template dropdowns."""
    conn = db_connect()
    mithrix = conn.cursor()
    try:
        mithrix.execute(
            'SELECT role_id, role_name FROM "role" ORDER BY role_id')
        return mithrix.fetchall()
    except Exception as exc:
        logger.error("Database error: %s", exc)
        return []
    finally:
        mithrix.close()
        conn.close()

def update_user_role(user_id, new_role_id, acting_admin_id):
    """Change a user's role and write an audit entry."""
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        # capture old role for audit
        mithrix.execute(
            'SELECT role_id FROM "user" WHERE user_id = %s', (user_id,)
        )
        row = mithrix.fetchone()
        old_role_id = row["role_id"] if row else None

        mithrix.execute(
            'UPDATE "user" SET role_id = %s WHERE user_id = %s',
            (new_role_id, user_id),
        )

        log_audit(
            mithrix, acting_admin_id,
            "role_change", "user", user_id,
            old_values=str(old_role_id),
            new_values=str(new_role_id),
        )

        conn.commit()
        return True, None
    except Exception as exc:
        conn.rollback()
        logger.error("Database error: %s", exc)
        return False, "A database error occurred. Please try again."
    finally:
        mithrix.close()
        conn.close()

def delete_user_account(user_id, acting_admin_id):
    """
    Hard-delete a user and all dependent rows.
    Order matters — FK constraints cascade from least to most dependent.
    """
    conn = db_connect()
    mithrix = conn.cursor()
    try:
        # audit first, while user still exists
        log_audit(mithrix, acting_admin_id, "delete_user", "user", user_id)

        # remove auth chain
        mithrix.execute("""
            DELETE FROM slug WHERE user_id = %s
        """, (user_id,))

        mithrix.execute("""
            DELETE FROM login   WHERE user_id = %s
        """, (user_id,))

        mithrix.execute("""
            DELETE FROM logOut  WHERE user_id = %s
        """, (user_id,))

        mithrix.execute("""
            DELETE FROM signup  WHERE user_id = %s
        """, (user_id,))

        mithrix.execute("""
            DELETE FROM contact WHERE user_id = %s
        """, (user_id,))

        # finally the user row itself
        mithrix.execute("""
            DELETE FROM "user"  WHERE user_id = %s
        """, (user_id,))

        conn.commit()
        return True, None
    except Exception as exc:
        conn.rollback()
        logger.error("Database error: %s", exc)
        return False, "A database error occurred. Please try again."
    finally:
        mithrix.close()
        conn.close()
