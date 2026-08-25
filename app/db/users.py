"""
Manage Users: listing, contact info, roles, and account deletion.
"""
import logging
import psycopg2.extras
from datetime import datetime, timezone
from werkzeug.security import check_password_hash

from app.db.connection import db_connect
from app.db.audit import log_audit

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


def get_users(search=None, role_id=None, status=None, page=1, page_size=20):
    """
    Fetch users for the Manage Users list — search by name/university
    no./email, filter by role or account_status, paginated.
    Returns (rows: list[RealDictRow], total: int).
    """
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        conditions = []
        params = []

        if search:
            conditions.append("""(
                CONCAT_WS(' ', u.user_first_name, u.user_middle_name, u.user_last_name) ILIKE %s
                OR u.university_no ILIKE %s
                OR c.contact_value ILIKE %s
            )""")
            like = f"%{search}%"
            params += [like, like, like]

        if role_id:
            conditions.append("u.role_id = %s")
            params.append(role_id)

        if status:
            conditions.append("u.account_status = %s")
            params.append(status)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        mithrix.execute(f"""
            SELECT COUNT(*) AS total
            FROM "user" u
            JOIN role r ON u.role_id = r.role_id
            LEFT JOIN contact c ON c.user_id = u.user_id AND c.contact_type = 'email' AND c.is_primary = TRUE
            {where}
        """, params)
        total = mithrix.fetchone()["total"]

        offset = (page - 1) * page_size

        mithrix.execute(f"""
            SELECT u.user_id,
                   u.role_id,
                   u.account_status,
                   CONCAT_WS(' ', u.user_first_name, u.user_middle_name, u.user_last_name) AS full_name,
                   u.university_no,
                   r.role_name AS role,
                   c.contact_value AS email
            FROM "user" u
            JOIN role r ON u.role_id = r.role_id
            LEFT JOIN contact c ON c.user_id = u.user_id AND c.contact_type = 'email' AND c.is_primary = TRUE
            {where}
            ORDER BY u.user_first_name, u.user_last_name
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])

        return mithrix.fetchall(), total
    except Exception as exc:
        logger.error("Database error: %s", exc)
        return [], 0
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
    if str(user_id) == str(acting_admin_id):
        return False, "You can't change your own role from here."

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

def _run_delete_cascade(mithrix, conn, user_id, acting_id):
    """
    Shared by delete_user_account() (admin-initiated) and
    delete_own_account() (self-service) — the actual hard-delete cascade.
    Order matters — FK constraints cascade from least to most dependent.
    """
    conn = db_connect()
    mithrix = conn.cursor()
    # audit first, while user still exists
    log_audit(mithrix, acting_id, "delete_user", "user", user_id)

    # remove auth chain
    mithrix.execute('DELETE FROM slug WHERE user_id = %s', (user_id,))
    mithrix.execute('DELETE FROM login   WHERE user_id = %s', (user_id,))
    mithrix.execute('DELETE FROM logOut  WHERE user_id = %s', (user_id,))
    mithrix.execute('DELETE FROM signup  WHERE user_id = %s', (user_id,))
    mithrix.execute('DELETE FROM contact WHERE user_id = %s', (user_id,))

    # Temporary fix for now, !TODO
    mithrix.execute('DELETE FROM "audit" WHERE user_id = %s', (user_id,))
    mithrix.execute('DELETE FROM "request" WHERE user_id = %s', (user_id,))

    # finally the user row itself
    mithrix.execute('DELETE FROM "user"  WHERE user_id = %s', (user_id,))
    

    conn.commit()


def delete_user_account(user_id, acting_admin_id):
    """Admin-initiated delete (Manage Users) — an admin can't delete
    their own account from here; see delete_own_account() for the
    self-service path from User Information, which requires a password
    instead and carries its own last-admin safety check."""
    if str(user_id) == str(acting_admin_id):
        return False, "You can't delete your own account from here."

    conn = db_connect()
    mithrix = conn.cursor()
    try:
        _run_delete_cascade(mithrix, conn, user_id, acting_admin_id)
        return True, None
    except Exception as exc:
        conn.rollback()
        logger.error("Database error: %s", exc)
        return False, "A database error occurred. Please try again."
    finally:
        mithrix.close()
        conn.close()


def delete_own_account(user_id, password):
    """
    Self-service account deletion from User Information — requires the
    current password (same verification pattern as change_own_password())
    since this is irreversible, and blocks deletion if the account is
    the system's only remaining Admin (would otherwise lock out all
    admin access with no recovery path).
    """
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        mithrix.execute("""
            SELECT r.password AS password_hash, u.role_id
            FROM "user" u
            JOIN slug sl ON sl.user_id = u.user_id AND sl.is_current = TRUE
            JOIN ror r ON r.password_id = sl.password_id
            WHERE u.user_id = %s
            LIMIT 1
        """, (user_id,))
        row = mithrix.fetchone()

        if not row or not check_password_hash(row["password_hash"], password):
            return False, "Incorrect password."

        if row["role_id"] == 3:  # Admin
            mithrix.execute(
                'SELECT COUNT(*) AS n FROM "user" WHERE role_id = 3 AND account_status = \'active\''
            )
            admin_count = mithrix.fetchone()["n"]
            if admin_count <= 1:
                return False, "You're the only remaining Admin — deleting your account would lock everyone out. Assign another Admin first."
    except Exception as exc:
        logger.error("Database error: %s", exc)
        return False, "A database error occurred. Please try again."
    finally:
        mithrix.close()
        conn.close()

    conn = db_connect()
    mithrix = conn.cursor()
    try:
        _run_delete_cascade(mithrix, conn, user_id, user_id)
        return True, None
    except Exception as exc:
        conn.rollback()
        logger.error("Database error: %s", exc)
        return False, "A database error occurred. Please try again."
    finally:
        mithrix.close()
        conn.close()


def set_account_status(user_id, new_status, acting_admin_id):
    """
    Soft-suspend/restore an account — 'deactivated' blocks sign-in
    (same check sign_in() already does for account_status) without
    destroying any data, unlike delete_user_account()'s permanent
    hard-delete. Mirrors the Capstone Repository's own soft-delete
    (Recycle Bin) pattern, which Manage Users previously had no
    equivalent of.
    """
    if str(user_id) == str(acting_admin_id):
        return False, "You can't deactivate your own account from here."

    if new_status not in ("active", "deactivated"):
        return False, "Invalid account status."

    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        mithrix.execute(
            'SELECT account_status FROM "user" WHERE user_id = %s', (user_id,)
        )
        row = mithrix.fetchone()
        old_status = row["account_status"] if row else None

        mithrix.execute(
            'UPDATE "user" SET account_status = %s WHERE user_id = %s',
            (new_status, user_id),
        )

        log_audit(
            mithrix, acting_admin_id,
            "account_status_change", "user", user_id,
            old_values=old_status, new_values=new_status,
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


# ── Promotion Request (DFD 2.4.1/2.4.2) ─────────────────────────────
# A logged-in user requesting a *different* role — distinct from
# account verification (new signups being activated). Approving
# actually changes role_id; verification approval never touches role,
# only account_status. Shares the request table via request_type =
# 'promotion' + target_role_id, mirroring the verification_* pattern
# in app/db/auth.py.

def submit_promotion_request(user_id, target_role_id, reason):
    """One pending promotion request per user at a time — a second
    submission while one is still pending is rejected rather than
    silently creating a duplicate for admins to sort out."""
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    now = datetime.now(timezone.utc)
    try:
        mithrix.execute("""
            SELECT request_id FROM request
            WHERE user_id = %s AND request_type = 'promotion' AND request_status = 'pending'
        """, (user_id,))
        if mithrix.fetchone():
            return False, "You already have a pending promotion request."

        mithrix.execute("""
            SELECT role_id FROM "user" WHERE user_id = %s
        """, (user_id,))
        row = mithrix.fetchone()
        if row and row["role_id"] == target_role_id:
            return False, "You already have that role."

        mithrix.execute("""
            INSERT INTO request(user_id, request_type, target_role_id, request_status, request_reason, request_date)
            VALUES (%s, 'promotion', %s, 'pending', %s, %s)
            RETURNING request_id
        """, (user_id, target_role_id, reason, now))
        request_id = mithrix.fetchone()["request_id"]

        log_audit(mithrix, user_id, "promotion_request", "request", request_id)

        conn.commit()
        return True, None
    except Exception as exc:
        conn.rollback()
        logger.error("Database error: %s", exc)
        return False, "A database error occurred. Please try again."
    finally:
        mithrix.close()
        conn.close()


def get_pending_promotion_requests():
    """Pending promotion requests for the Manage Users panel — kept as
    its own query rather than reused from a capstone-joined listing,
    since promotion requests have capstone_id = NULL (same reasoning
    as get_pending_verifications())."""
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        mithrix.execute("""
            SELECT r.request_id, r.user_id, r.request_reason, r.request_date,
                   CONCAT_WS(' ', u.user_first_name, u.user_middle_name, u.user_last_name) AS full_name,
                   u.university_no,
                   cur_role.role_name AS current_role,
                   tgt_role.role_name AS target_role
            FROM request r
            JOIN "user" u ON u.user_id = r.user_id
            JOIN role cur_role ON cur_role.role_id = u.role_id
            JOIN role tgt_role ON tgt_role.role_id = r.target_role_id
            WHERE r.request_type = 'promotion'
              AND r.request_status = 'pending'
            ORDER BY r.request_date ASC
        """)
        return mithrix.fetchall()
    except Exception as exc:
        logger.error("Database error: %s", exc)
        return []
    finally:
        mithrix.close()
        conn.close()


def get_own_promotion_requests(user_id):
    """A user's own promotion request history — feeds the Request
    Promotion card on User Information."""
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        mithrix.execute("""
            SELECT r.request_id, r.request_status, r.request_reason, r.request_date,
                   r.status_reason, target_role.role_name AS target_role
            FROM request r
            JOIN role target_role ON target_role.role_id = r.target_role_id
            WHERE r.user_id = %s AND r.request_type = 'promotion'
            ORDER BY r.request_date DESC
        """, (user_id,))
        return mithrix.fetchall()
    except Exception as exc:
        logger.error("Database error: %s", exc)
        return []
    finally:
        mithrix.close()
        conn.close()


def review_promotion_request(request_id, decision, status_reason, reviewed_by):
    """
    Approve/reject a promotion request. Unlike review_verification_request()
    (flips account_status), approving here changes the user's actual
    role_id to the requested target role.

    decision: 'approved' or 'rejected'
    """
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    now = datetime.now(timezone.utc)

    try:
        mithrix.execute("""
            SELECT user_id, target_role_id FROM request
            WHERE request_id = %s AND request_type = 'promotion'
            FOR UPDATE
        """, (request_id,))
        row = mithrix.fetchone()
        if not row:
            conn.rollback()
            return False, "Promotion request not found."

        mithrix.execute("""
            UPDATE request SET
                request_status = %s,
                status_reason = %s,
                reviewed_by = %s,
                decision_date = %s
            WHERE request_id = %s
        """, (decision, status_reason, reviewed_by, now, request_id))

        if decision == "approved":
            mithrix.execute("""
                UPDATE "user" SET role_id = %s
                WHERE user_id = %s
            """, (row["target_role_id"], row["user_id"]))

        log_audit(mithrix, reviewed_by, "review_promotion_request", "request", request_id,
                   new_values=decision)

        conn.commit()
        return True, None
    except Exception as exc:
        conn.rollback()
        logger.error("Database error: %s", exc)
        return False, "A database error occurred. Please try again."
    finally:
        mithrix.close()
        conn.close()


def cancel_promotion_request(request_id, user_id):
    """Self-service cancel — mirrors cancel_manuscript_request(), scoped
    to request_type = 'promotion' so it can't be used to cancel a
    different kind of request by request_id guessing."""
    conn = db_connect()
    mithrix = conn.cursor()
    try:
        mithrix.execute("""
            UPDATE request
            SET request_status = 'cancelled'
            WHERE request_id = %s AND user_id = %s
              AND request_type = 'promotion' AND request_status = 'pending'
        """, (request_id, user_id))

        log_audit(mithrix, user_id, "cancel_promotion_request", "request", request_id)

        conn.commit()
        return True, None
    except Exception as exc:
        conn.rollback()
        logger.error("Database error: %s", exc)
        return False, "A database error occurred. Please try again."
    finally:
        mithrix.close()
        conn.close()
