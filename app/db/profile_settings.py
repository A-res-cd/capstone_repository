"""Atomic self-service profile changes."""
from app.db.connection import db_connect


def swap_avatar(user_id, filename):
    conn = db_connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT avatar_filename FROM "user" WHERE user_id = %s FOR UPDATE', (user_id,))
            row = cursor.fetchone()
            if row is None:
                raise ValueError('Account not found.')
            cursor.execute('UPDATE "user" SET avatar_filename = %s WHERE user_id = %s', (filename, user_id))
        conn.commit()
        return row[0]
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
