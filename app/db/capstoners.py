"""Capstoner approval is independent of login verification, roles and credits."""
from datetime import datetime, timezone
import logging

import psycopg2.extras

from app.db.audit import log_audit
from app.db.connection import db_connect

logger = logging.getLogger(__name__)


def _read(query, params=()):
    conn = db_connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()
    finally:
        conn.close()


def _write(operation):
    conn = db_connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            operation(cursor)
        conn.commit()
        return True, None
    except ValueError as exc:
        conn.rollback()
        return False, str(exc)
    except Exception as exc:
        conn.rollback()
        logger.error("Capstoner database error: %s", exc)
        return False, "Could not save the capstoner change. Please try again."
    finally:
        conn.close()


def _lock_accounts(cursor, user_id, reviewer_id=None):
    if reviewer_id == user_id:
        raise ValueError("Another capstone professor must verify your own authorship.")
    ids = [user_id] if reviewer_id is None else [user_id, reviewer_id]
    cursor.execute('''
        SELECT user_id, account_status, role_id FROM "user"
        WHERE user_id = ANY(%s) ORDER BY user_id FOR NO KEY UPDATE
    ''', (ids,))
    accounts = {row["user_id"]: row for row in cursor.fetchall()}
    if reviewer_id is not None:
        reviewer = accounts.get(reviewer_id)
        if not reviewer or reviewer["role_id"] != 4 or reviewer["account_status"] != "active":
            raise ValueError("Only an active capstone professor can verify capstoners.")
    account = accounts.get(user_id)
    if not account or account["account_status"] != "active":
        raise ValueError("The user account must be verified and active first.")


def get_capstoner_registration(user_id):
    rows = _read("""
        SELECT request_id, request_status, request_reason, request_date,
               decision_date, status_reason
        FROM request WHERE user_id = %s AND request_type = 'capstoner'
        ORDER BY request_id DESC LIMIT 1
    """, (user_id,))
    return rows[0] if rows else None


def submit_capstoner_registration(user_id, reason):
    reason = (reason or "").strip()

    def operation(cursor):
        if not reason or len(reason) > 2000:
            raise ValueError("Provide capstone details using 1–2000 characters.")
        _lock_accounts(cursor, user_id)
        cursor.execute("""
            SELECT request_id FROM request WHERE user_id = %s
              AND request_type = 'capstoner' AND request_status IN ('pending', 'approved')
        """, (user_id,))
        if cursor.fetchone():
            raise ValueError("You are already approved or have a pending capstoner request.")
        cursor.execute("""
            INSERT INTO request (user_id, request_type, request_status, request_reason, request_date)
            VALUES (%s, 'capstoner', 'pending', %s, %s) RETURNING request_id
        """, (user_id, reason, datetime.now(timezone.utc)))
        log_audit(cursor, user_id, "request_capstoner", "request", cursor.fetchone()["request_id"])

    return _write(operation)


def get_pending_capstoners():
    return _read("""
        SELECT r.request_id, r.user_id, r.request_reason, r.request_date,
               CONCAT_WS(' ', u.user_first_name, u.user_middle_name, u.user_last_name) AS full_name,
               u.university_no, u.account_status
        FROM request r JOIN "user" u ON u.user_id = r.user_id
        WHERE r.request_type = 'capstoner' AND r.request_status = 'pending'
        ORDER BY r.request_date, r.request_id
    """)


def review_capstoner_registration(request_id, decision, reason, reviewer_id):
    reason = (reason or "").strip()

    def operation(cursor):
        if reviewer_id is None:
            raise ValueError("A capstone professor must be signed in to review this request.")
        if decision not in {"approved", "rejected"} or len(reason) > 1000:
            raise ValueError("Choose approve or reject and keep feedback within 1000 characters.")
        if decision == "rejected" and not reason:
            raise ValueError("Explain why the capstoner request was rejected.")
        cursor.execute("SELECT user_id FROM request WHERE request_id = %s AND request_type = 'capstoner'", (request_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError("Capstoner request not found.")
        _lock_accounts(cursor, row["user_id"], reviewer_id)
        cursor.execute("""
            UPDATE request SET request_status = %s, status_reason = %s,
                reviewed_by = %s, decision_date = %s, notification_seen_at = NULL
            WHERE request_id = %s AND request_type = 'capstoner' AND request_status = 'pending'
            RETURNING request_id
        """, (decision, reason or None, reviewer_id, datetime.now(timezone.utc), request_id))
        if not cursor.fetchone():
            raise ValueError("This request was already reviewed. Refresh the page.")
        log_audit(cursor, reviewer_id, "review_capstoner", "request", request_id, new_values=decision)
        # No role/account-status changes and no author/capauth writes here.

    return _write(operation)


def get_capstoner_assignment_choices():
    accounts = _read('''
        SELECT user_id, CONCAT_WS(' ', user_first_name, user_middle_name, user_last_name) AS full_name,
               university_no FROM "user" WHERE account_status = 'active'
        ORDER BY user_last_name, user_first_name, user_id
    ''')
    credits = _read("""
        SELECT ca.capstone_id, ca.author_id, c.capstone_title, c.capstone_year,
               CONCAT_WS(' ', a.aut_first_name, a.aut_middle_name, a.aut_last_name) AS author_name
        FROM capauth ca JOIN author a ON a.author_id = ca.author_id
        JOIN capstone c ON c.capstone_id = ca.capstone_id
        WHERE ca.role = 'Author' AND a.user_id IS NULL AND c.is_archived IS NOT TRUE
        ORDER BY c.capstone_title, ca.author_order, a.author_id
    """)
    return accounts, credits


def assign_capstoner_credit(capstone_id, author_id, user_id, reviewer_id):
    """Verify and link one unclaimed credit, atomically, without name matching."""
    def operation(cursor):
        if reviewer_id is None:
            raise ValueError("A capstone professor must be signed in to assign an author credit.")
        cursor.execute("SELECT capstone_id FROM capstone WHERE capstone_id = %s AND is_archived IS NOT TRUE FOR UPDATE", (capstone_id,))
        if not cursor.fetchone():
            raise ValueError("Choose a capstone currently in the archive.")
        _lock_accounts(cursor, user_id, reviewer_id)
        cursor.execute("""
            SELECT a.*, EXISTS (SELECT 1 FROM capauth other WHERE other.author_id = a.author_id
                               AND other.capstone_id <> %s) AS shared
            FROM author a JOIN capauth ca ON ca.author_id = a.author_id
            WHERE ca.capstone_id = %s AND ca.author_id = %s AND ca.role = 'Author'
            FOR UPDATE OF a, ca
        """, (capstone_id, capstone_id, author_id))
        author = cursor.fetchone()
        if not author:
            raise ValueError("Author credit not found on this capstone.")
        if author["user_id"] is not None:
            raise ValueError("This author credit is already linked. No account was overwritten.")
        cursor.execute("""
            SELECT 1 FROM capauth ca JOIN author a ON a.author_id = ca.author_id
            WHERE ca.capstone_id = %s AND ca.role = 'Author' AND a.user_id = %s
        """, (capstone_id, user_id))
        if cursor.fetchone():
            raise ValueError("This account already has an author credit on this capstone.")

        linked_author_id = author_id
        if author["shared"]:
            cursor.execute("""
                INSERT INTO author (aut_first_name, aut_middle_name, aut_last_name, user_id)
                VALUES (%s, %s, %s, %s) RETURNING author_id
            """, (author["aut_first_name"], author["aut_middle_name"], author["aut_last_name"], user_id))
            linked_author_id = cursor.fetchone()["author_id"]
            cursor.execute("UPDATE capauth SET author_id = %s WHERE capstone_id = %s AND author_id = %s",
                           (linked_author_id, capstone_id, author_id))
        else:
            cursor.execute("UPDATE author SET user_id = %s WHERE author_id = %s", (user_id, author_id))

        cursor.execute("""
            SELECT request_id, request_status FROM request WHERE user_id = %s
              AND request_type = 'capstoner' AND request_status IN ('pending', 'approved') FOR UPDATE
        """, (user_id,))
        registration = cursor.fetchone()
        now = datetime.now(timezone.utc)
        feedback = "Authorship verified by a capstone professor through direct author assignment."
        if not registration:
            cursor.execute("""
                INSERT INTO request (user_id, request_type, request_status, request_reason,
                                     request_date, decision_date, reviewed_by, status_reason)
                VALUES (%s, 'capstoner', 'approved', %s, %s, %s, %s, %s) RETURNING request_id
            """, (user_id, feedback, now, now, reviewer_id, feedback))
            registration = {"request_id": cursor.fetchone()["request_id"], "request_status": "new"}
        elif registration["request_status"] == "pending":
            cursor.execute("""
                UPDATE request SET request_status = 'approved', status_reason = %s, reviewed_by = %s,
                    decision_date = %s, notification_seen_at = NULL WHERE request_id = %s
            """, (feedback, reviewer_id, now, registration["request_id"]))
        if registration["request_status"] != "approved":
            log_audit(cursor, reviewer_id, "approve_capstoner_by_assignment", "request", registration["request_id"])
        log_audit(cursor, reviewer_id, "assign_capstoner_credit", "capstone", capstone_id,
                  new_values=f"author_id={linked_author_id}; user_id={user_id}")

    return _write(operation)
