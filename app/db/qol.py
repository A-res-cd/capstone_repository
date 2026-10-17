"""User notifications and pending-request counts."""
import logging
from datetime import datetime, timezone

import psycopg2.extras

from app.db.connection import db_connect


logger = logging.getLogger(__name__)


def get_user_notification_summary(user_id, limit=6):
    conn = None
    cursor = None
    try:
        conn = db_connect()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            """
            SELECT
                r.request_id,
                r.request_type,
                r.request_status,
                r.decision_date,
                r.status_reason,
                r.notification_seen_at,
                c.capstone_title
            FROM request r
            LEFT JOIN capstone c ON c.capstone_id = r.capstone_id
            WHERE r.user_id = %s
              AND r.request_type IS DISTINCT FROM 'promotion'
              AND r.decision_date IS NOT NULL
              AND r.request_status IN ('approved', 'rejected')
            ORDER BY r.decision_date DESC, r.request_id DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        notifications = list(cursor.fetchall())

        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM request
            WHERE user_id = %s
              AND request_type IS DISTINCT FROM 'promotion'
              AND decision_date IS NOT NULL
              AND request_status IN ('approved', 'rejected')
              AND notification_seen_at IS NULL
            """,
            (user_id,),
        )
        unread_count = cursor.fetchone()["total"]
        return notifications, unread_count
    except Exception as exc:
        logger.error("Database error loading notifications: %s", exc)
        return [], 0
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def get_page_nav_summary(user_id, is_admin=False, limit=6):
    """Fetch notifications and optional admin badges in one DB round trip."""
    conn = None
    cursor = None
    try:
        conn = db_connect()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # Ordinary readers need only their own notifications, not a table-wide
        # aggregate whose filters are always false. Keep admin badge SQL intact.
        pending_sql = """
                COUNT(*) FILTER (
                    WHERE %s AND request_status = 'pending'
                      AND (request_type = 'manuscript'
                           OR (request_type IS NULL AND capstone_id IS NOT NULL))
                ) AS manuscript_requests,
                COUNT(*) FILTER (
                    WHERE %s AND request_status = 'pending'
                      AND request_type LIKE 'verification_%%'
                ) AS user_requests
            FROM request
        """ if is_admin else "0::bigint AS manuscript_requests, 0::bigint AS user_requests"
        params = (user_id, limit, user_id) + ((is_admin, is_admin) if is_admin else ())
        cursor.execute(
            f"""
            SELECT
                COALESCE((
                    SELECT json_agg(to_jsonb(recent))
                    FROM (
                        SELECT r.request_id, r.request_type, r.request_status,
                               r.decision_date, r.status_reason,
                               r.notification_seen_at, c.capstone_title
                        FROM request r
                        LEFT JOIN capstone c ON c.capstone_id = r.capstone_id
                        WHERE r.user_id = %s
                          AND r.request_type IS DISTINCT FROM 'promotion'
                          AND r.decision_date IS NOT NULL
                          AND r.request_status IN ('approved', 'rejected')
                        ORDER BY r.decision_date DESC, r.request_id DESC
                        LIMIT %s
                    ) recent
                ), '[]'::json) AS notifications,
                (SELECT COUNT(*) FROM request
                 WHERE user_id = %s
                   AND request_type IS DISTINCT FROM 'promotion'
                   AND decision_date IS NOT NULL
                   AND request_status IN ('approved', 'rejected')
                   AND notification_seen_at IS NULL) AS unread_count,
                {pending_sql}
            """,
            params,
        )
        row = cursor.fetchone()
        notifications = row["notifications"] or []
        for item in notifications:
            for key in ("decision_date", "notification_seen_at"):
                if item.get(key):
                    item[key] = datetime.fromisoformat(item[key])
        pending_counts = ({
            "admin.view_requests": row["manuscript_requests"],
            "admin.manage_users": row["user_requests"],
        } if is_admin else {})
        return notifications, row["unread_count"], pending_counts
    except Exception as exc:
        logger.error("Database error loading page navigation summary: %s", exc)
        return [], 0, {}
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def mark_all_notifications_read(user_id):
    conn = db_connect()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE request
            SET notification_seen_at = %s
            WHERE user_id = %s
              AND request_type IS DISTINCT FROM 'promotion'
              AND decision_date IS NOT NULL
              AND request_status IN ('approved', 'rejected')
              AND notification_seen_at IS NULL
            """,
            (datetime.now(timezone.utc), user_id),
        )
        conn.commit()
        return True
    except Exception as exc:
        conn.rollback()
        logger.error("Database error marking notifications read: %s", exc)
        return False
    finally:
        cursor.close()
        conn.close()


def get_admin_pending_nav_counts():
    """Pending work shown as red dots beside the two admin nav links."""
    conn = db_connect()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cursor.execute("""
            SELECT
                COUNT(*) FILTER (
                    WHERE request_status = 'pending'
                      AND (request_type = 'manuscript'
                           OR (request_type IS NULL AND capstone_id IS NOT NULL))
                ) AS manuscript_requests,
                COUNT(*) FILTER (
                    WHERE request_status = 'pending'
                      AND request_type LIKE 'verification_%'
                ) AS user_requests
            FROM request
        """)
        row = cursor.fetchone()
        return {
            "admin.view_requests": row["manuscript_requests"],
            "admin.manage_users": row["user_requests"],
        }
    except Exception as exc:
        logger.error("Database error loading admin nav counts: %s", exc)
        return {}
    finally:
        cursor.close()
        conn.close()
