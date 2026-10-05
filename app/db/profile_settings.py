"""Atomic self-service profile changes."""
from app.db.connection import db_connect
from app.db.audit import log_audit


def save_contact_settings(user_id, email, phone, preference):
    conn = db_connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT user_id FROM "user" WHERE user_id = %s FOR UPDATE', (user_id,))
            if not cursor.fetchone():
                raise ValueError('Account not found.')
            for kind, value in [('email', email), ('phone', phone)]:
                cursor.execute('SELECT contact_id FROM contact WHERE user_id = %s AND contact_type = %s ORDER BY is_primary DESC, contact_id DESC LIMIT 1', (user_id, kind))
                row = cursor.fetchone()
                if row:
                    cursor.execute('UPDATE contact SET is_primary = FALSE WHERE user_id = %s AND contact_type = %s', (user_id, kind))
                    cursor.execute('UPDATE contact SET contact_value = %s, is_primary = TRUE WHERE contact_id = %s', (value, row[0]))
                elif value:
                    cursor.execute('INSERT INTO contact (user_id, contact_type, contact_value, is_primary, created_at) VALUES (%s, %s, %s, TRUE, CURRENT_TIMESTAMP)', (user_id, kind, value))
            cursor.execute('UPDATE "user" SET preferred_contact = %s WHERE user_id = %s', (preference, user_id))
            log_audit(cursor, user_id, 'update_contact', 'user', user_id,
                      new_values='Preferred contact: ' + preference)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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
