"""Deduplicated capstone activity and privacy-safe author notifications."""

import logging
from datetime import datetime, timezone

import psycopg2.extras

from app.db.connection import db_connect


logger = logging.getLogger(__name__)

EVENT_COPY = {
    "view": ("capstone_view", "Capstone view recorded", "Your linked capstone received a view."),
    "citation": ("capstone_citation", "Capstone citation recorded", "Your linked capstone was cited."),
    "request": ("capstone_request", "New manuscript request", "Someone requested access to your linked capstone."),
}


def record_capstone_activity_in_cursor(
    cursor,
    capstone_id,
    actor_user_id,
    event_type,
    event_variant=None,
    request_id=None,
    occurred_at=None,
):
    """Insert one event and notify linked authors inside the caller transaction."""
    if event_type not in EVENT_COPY:
        raise ValueError("Unsupported capstone activity type.")
    if not actor_user_id:
        raise ValueError("Capstone activity requires an authenticated actor.")

    occurred_at = occurred_at or datetime.now(timezone.utc)
    activity_day = occurred_at.date()
    if event_type == "request":
        cursor.execute(
            """
            INSERT INTO capstone_activity
                (capstone_id, actor_user_id, event_type, event_variant,
                 activity_day, request_id, occurred_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (request_id) DO NOTHING
            RETURNING activity_id
            """,
            (capstone_id, actor_user_id, event_type, event_variant,
             activity_day, request_id, occurred_at),
        )
    else:
        cursor.execute(
            """
            INSERT INTO capstone_activity
                (capstone_id, actor_user_id, event_type, event_variant,
                 activity_day, occurred_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (capstone_id, actor_user_id, event_type, activity_day)
                WHERE event_type IN ('view', 'citation')
                AND actor_user_id IS NOT NULL
            DO NOTHING
            RETURNING activity_id
            """,
            (capstone_id, actor_user_id, event_type, event_variant,
             activity_day, occurred_at),
        )

    row = cursor.fetchone()
    if not row:
        return False
    activity_id = row["activity_id"] if isinstance(row, dict) else row[0]
    notification_type, title, message = EVENT_COPY[event_type]

    cursor.execute(
        """
        SELECT DISTINCT a.user_id
        FROM capauth ca
        JOIN author a ON a.author_id = ca.author_id
        WHERE ca.capstone_id = %s
          AND ca.role = 'Author'
          AND a.user_id IS NOT NULL
          AND a.user_id <> %s
        """,
        (capstone_id, actor_user_id),
    )
    recipients = cursor.fetchall()
    for recipient in recipients:
        recipient_id = recipient["user_id"] if isinstance(recipient, dict) else recipient[0]
        cursor.execute(
            """
            INSERT INTO notification
                (recipient_user_id, activity_id, notification_type,
                 notification_title, notification_message)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (activity_id, recipient_user_id) DO NOTHING
            """,
            (recipient_id, activity_id, notification_type, title, message),
        )
    return True


def record_capstone_activity(
    capstone_id,
    actor_user_id,
    event_type,
    event_variant=None,
    request_id=None,
    occurred_at=None,
):
    """Record activity without making a successful user action fail on telemetry."""
    conn = db_connect()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        created = record_capstone_activity_in_cursor(
            cursor, capstone_id, actor_user_id, event_type,
            event_variant=event_variant, request_id=request_id,
            occurred_at=occurred_at,
        )
        conn.commit()
        return created
    except Exception as exc:
        conn.rollback()
        logger.exception("Could not record capstone activity: %s", exc)
        return False
    finally:
        cursor.close()
        conn.close()


def get_author_activity_summary(user_id):
    conn = db_connect()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cursor.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE ca.event_type = 'view') AS views,
                COUNT(*) FILTER (WHERE ca.event_type = 'citation') AS citations,
                COUNT(*) FILTER (WHERE ca.event_type = 'request') AS requests
            FROM capstone_activity ca
            WHERE EXISTS (
                SELECT 1
                FROM capauth link
                JOIN author a ON a.author_id = link.author_id
                WHERE link.capstone_id = ca.capstone_id
                  AND link.role = 'Author'
                  AND a.user_id = %s
            )
            """,
            (user_id,),
        )
        row = cursor.fetchone() or {}
        return {
            "views": int(row.get("views") or 0),
            "citations": int(row.get("citations") or 0),
            "requests": int(row.get("requests") or 0),
        }
    except Exception as exc:
        logger.error("Database error loading author activity totals: %s", exc)
        return {"views": 0, "citations": 0, "requests": 0}
    finally:
        cursor.close()
        conn.close()


def get_recent_author_activity(user_id, limit=6):
    conn = db_connect()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cursor.execute(
            """
            SELECT ca.event_type, ca.event_variant, ca.occurred_at,
                   c.capstone_title
            FROM capstone_activity ca
            JOIN capstone c ON c.capstone_id = ca.capstone_id
            WHERE EXISTS (
                SELECT 1
                FROM capauth link
                JOIN author a ON a.author_id = link.author_id
                WHERE link.capstone_id = ca.capstone_id
                  AND link.role = 'Author'
                  AND a.user_id = %s
            )
            ORDER BY ca.occurred_at DESC, ca.activity_id DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        return cursor.fetchall()
    except Exception as exc:
        logger.error("Database error loading recent author activity: %s", exc)
        return []
    finally:
        cursor.close()
        conn.close()
