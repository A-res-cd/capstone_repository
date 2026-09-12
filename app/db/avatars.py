"""Database access for normalized user avatar metadata."""

import logging

import psycopg2.extras

from app.db.connection import db_connect


logger = logging.getLogger(__name__)


def get_user_avatar(user_id):
    conn = db_connect()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cursor.execute(
            """
            SELECT user_avatar_id, user_id, storage_key, original_name,
                   mime_type, file_size, width, height, uploaded_at, updated_at
            FROM user_avatar
            WHERE user_id = %s
            LIMIT 1
            """,
            (user_id,),
        )
        return cursor.fetchone()
    except Exception as exc:
        # Keeps old databases usable until the avatar migration is applied.
        logger.debug("Avatar metadata unavailable: %s", exc)
        return None
    finally:
        cursor.close()
        conn.close()


def upsert_user_avatar(user_id, metadata):
    conn = db_connect()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT storage_key FROM user_avatar WHERE user_id = %s FOR UPDATE",
            (user_id,),
        )
        previous = cursor.fetchone()
        previous_key = previous[0] if previous else None

        cursor.execute(
            """
            INSERT INTO user_avatar
                (user_id, storage_key, original_name, mime_type, file_size, width, height)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                storage_key = EXCLUDED.storage_key,
                original_name = EXCLUDED.original_name,
                mime_type = EXCLUDED.mime_type,
                file_size = EXCLUDED.file_size,
                width = EXCLUDED.width,
                height = EXCLUDED.height,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                user_id,
                metadata["storage_key"],
                metadata["original_name"],
                metadata["mime_type"],
                metadata["file_size"],
                metadata["width"],
                metadata["height"],
            ),
        )
        conn.commit()
        return previous_key
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()
