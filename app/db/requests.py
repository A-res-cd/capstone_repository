"""
Manuscript/full-view access requests: create, list, review
(approve/reject), cancel, and status breakdowns.
"""
import logging
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone

from app.db.connection import db_connect
from app.db.audit import log_audit
from datetime import datetime, timezone 

logger = logging.getLogger(__name__)


def request_fullview(user_id, capstone_id, request_reason):
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    now = datetime.now(timezone.utc)

    try:
        mithrix.execute(
            "SELECT pg_try_advisory_xact_lock(%s, %s) AS locked",
            (int(user_id), int(capstone_id)),
        )
        if not mithrix.fetchone()["locked"]:
            conn.rollback()
            return False, "This action is currently being processed by another user."

        mithrix.execute("""
            SELECT request_id
            FROM request
            WHERE user_id = %s
              AND capstone_id = %s
              AND request_type = 'manuscript'
              AND request_status IN ('pending', 'approved')
            FOR UPDATE
        """, (user_id, capstone_id))
        if mithrix.fetchone():
            conn.rollback()
            return False, "You already have a request for this capstone."

        mithrix.execute("""
            INSERT INTO request(user_id, capstone_id, request_status, request_reason, request_date, request_type)
            VALUES(%s, %s, 'pending', %s, %s, 'manuscript')
            RETURNING request_id
        """, (user_id, capstone_id, request_reason, now))

        request_id = mithrix.fetchone()["request_id"]
        log_audit(mithrix, user_id, "manuscript_request",
                  "manuscript_request", request_id)

        conn.commit()
        return True, None

    except Exception as exc:
        conn.rollback()
        logger.error("Database error: %s", exc)
        return False, "A database error occurred. Please try again."

    finally:
        mithrix.close()
        conn.close()

def get_all_requests(status=None):
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        query = """
            SELECT
                r.*,
                c.capstone_title,
                CONCAT_WS(' ', u.user_first_name, u.user_last_name) AS requester_name
            FROM request r
            JOIN capstone c ON c.capstone_id = r.capstone_id
            JOIN "user" u ON u.user_id = r.user_id
        """

        params = []

        if status and status != "all":
            query += " WHERE r.request_status = %s"
            params.append(status)

        query += " ORDER BY r.request_date DESC"

        mithrix.execute(query, params)

        return mithrix.fetchall()

    except Exception as exc:
        logger.error("Database error: %s", exc)
        return []

    finally:
        mithrix.close()
        conn.close()

def review_request(request_id, request_status, status_reason, reviewed_by):
    conn = db_connect()
    mithrix = conn.cursor()
    now = datetime.now(timezone.utc)

    try:
        mithrix.execute("""
            SELECT request_status
            FROM request
            WHERE request_id = %s
              AND (request_type = 'manuscript' OR (request_type IS NULL AND capstone_id IS NOT NULL))
            FOR UPDATE NOWAIT
        """, (request_id,))
        row = mithrix.fetchone()
        if not row:
            conn.rollback()
            return False, "Request not found."
        if row[0] != "pending":
            conn.rollback()
            return False, "This request has already been processed."

        mithrix.execute("""
            UPDATE request SET 
            request_status = %s,
            status_reason = %s,
            reviewed_by = %s,
            decision_date = %s
            WHERE request_id = %s
              AND (request_type = 'manuscript' OR (request_type IS NULL AND capstone_id IS NOT NULL))
        """, (request_status, status_reason, reviewed_by, now, request_id))

        log_audit(mithrix, reviewed_by, "review_request", "request", request_id,
                   new_values=request_status)

        conn.commit()
        return True, None
    except psycopg2.errors.LockNotAvailable:
        conn.rollback()
        return False, "This action is currently being processed by another user."
    except Exception as exc:
        conn.rollback()
        logger.error("Database error: %s", exc)
        return False, "A database error occurred. Please try again."

    finally:
        mithrix.close()
        conn.close()

# I DONT WANNA DO THIS ANYMOREEEEEEEEEE

def get_user_requests(user_id):
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        mithrix.execute("""
            SELECT r.*, c.capstone_title, c.capstone_id, s.specialization_name, c.capstone_year
            FROM request r
            JOIN capstone c ON c.capstone_id  = r.capstone_id
            JOIN specialization s ON s.specialization_id = c.specialization_id
            WHERE r.user_id = %s
            ORDER BY r.request_date DESC
        """, (user_id, ))

        return mithrix.fetchall()
    except Exception as exc:
        logger.error("Database error: %s", exc)
        return []

    finally:
        mithrix.close()
        conn.close()


def get_requestable_capstones(user_id):
    """Non-archived capstones the given user can open a *new* manuscript
    request for — i.e. everything except capstones they already have a
    pending or approved request on. Feeds the "Create New Request"
    picker on the My Requests page instead of sending the user back to
    the archive just to start a request."""
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        mithrix.execute("""
            SELECT c.capstone_id, c.capstone_title, c.capstone_year, s.specialization_name
            FROM capstone c
            JOIN specialization s ON s.specialization_id = c.specialization_id
            WHERE c.is_archived IS NOT TRUE
              AND c.capstone_id NOT IN (
                  SELECT r.capstone_id FROM request r
                  WHERE r.user_id = %s
                    AND r.request_status IN ('pending', 'approved')
                    AND r.capstone_id IS NOT NULL
              )
            ORDER BY c.capstone_title
        """, (user_id,))

        return mithrix.fetchall()
    except Exception as exc:
        logger.error("Database error: %s", exc)
        return []

    finally:
        mithrix.close()
        conn.close()


# ______________________________Admin Analytics___________________________

def cancel_manuscript_request(request_id, user_id):
    conn = db_connect()
    mithrix = conn.cursor()

    try:
        mithrix.execute("""
            SELECT request_status
            FROM request
            WHERE request_id = %s AND user_id = %s
              AND (request_type = 'manuscript' OR (request_type IS NULL AND capstone_id IS NOT NULL))
            FOR UPDATE NOWAIT
        """, (request_id, user_id))
        row = mithrix.fetchone()
        if not row:
            conn.rollback()
            return False, "Request not found."
        if row[0] != "pending":
            conn.rollback()
            return False, "This request can no longer be cancelled â€” it may have already been decided or cancelled."

        mithrix.execute("""
            UPDATE request
            SET request_status = 'cancelled'
            WHERE request_id = %s AND user_id = %s
            AND request_status = 'pending'
            AND (request_type = 'manuscript' OR (request_type IS NULL AND capstone_id IS NOT NULL))
        """, (request_id, user_id))

        if mithrix.rowcount == 0:
            conn.rollback()
            return False, "This request can no longer be cancelled — it may have already been decided or cancelled."

        log_audit(mithrix, user_id, "cancel_request", "request", request_id)

        conn.commit()
        return True, None
    except psycopg2.errors.LockNotAvailable:
        conn.rollback()
        return False, "This action is currently being processed by another user."

    except Exception as exc:
        conn.rollback()
        logger.error("Database error: %s", exc)
        return False, "A database error occurred. Please try again."

    finally:
        mithrix.close()
        conn.close()

def get_requests_by_status():
    """Request count grouped by status — for the Analytics donut chart."""
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        mithrix.execute("""
            SELECT request_status, COUNT(*) AS total
            FROM request
            GROUP BY request_status
            ORDER BY total DESC
        """)
        return mithrix.fetchall(), None
    except Exception as exc:
        logger.error("Database error: %s", exc)
        return [], "Request analytics are temporarily unavailable."
    finally:
        mithrix.close()
        conn.close()
