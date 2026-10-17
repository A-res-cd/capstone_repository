"""Recovery changes use a separate proof and the account's current credential."""
from contextlib import closing
import hashlib
import secrets
import uuid

import psycopg2.extras
from werkzeug.security import check_password_hash, generate_password_hash
from app.db.connection import db_connect
from app.db.audit import log_audit

EXPIRY_MINUTES = 15
MAX_ATTEMPTS = 5


def _session_hash(binding):
    if not isinstance(binding, str) or not binding:
        raise ValueError('Start the contact change again.')
    return hashlib.sha256(binding.encode()).hexdigest()


def _credential(cursor, user_id):
    cursor.execute('SELECT user_id FROM "user" WHERE user_id = %s FOR UPDATE', (user_id,))
    if not cursor.fetchone():
        raise ValueError('Account not found.')
    cursor.execute('''SELECT sl.password_id, r.password FROM slug sl
                      JOIN ror r ON r.password_id = sl.password_id
                      WHERE sl.user_id = %s AND sl.is_current = TRUE''', (user_id,))
    return cursor.fetchone()


def request_change(user_id, password, binding, values, preference):
    session_hash = _session_hash(binding)
    with closing(db_connect()) as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        credential = _credential(cursor, user_id)
        if (not credential or not isinstance(password, str) or not 1 <= len(password) <= 1024
                or not check_password_hash(credential['password'], password)):
            log_audit(cursor, user_id, 'contact_change_rejected', 'user', user_id)
            conn.commit()
            raise ValueError('Current password is incorrect.')
        cursor.execute('''SELECT contact_type, contact_value FROM contact WHERE user_id = %s
                          ORDER BY is_primary, contact_id FOR UPDATE''', (user_id,))
        existing = {row['contact_type']: row['contact_value'] for row in cursor.fetchall()}
        changes = [(kind, value) for kind, value in values.items() if value != (existing.get(kind) or '')]
        if len(changes) > 1:
            raise ValueError('Change one recovery destination at a time.')
        if changes and not changes[0][1]:
            raise ValueError('Verify a replacement destination instead of removing a recovery channel.')
        if preference not in ('email', 'phone') or not values.get(preference):
            raise ValueError('Provide your preferred contact details.')
        if not changes:
            cursor.execute('UPDATE "user" SET preferred_contact = %s WHERE user_id = %s', (preference, user_id))
            conn.commit()
            return None
        kind, destination = changes[0]
        if len(destination) > 100:
            raise ValueError('Contact destination is too long.')
        cursor.execute('SELECT user_id FROM contact WHERE contact_type = %s AND contact_value = %s AND user_id <> %s',
                       (kind, destination, user_id))
        if cursor.fetchone():
            raise ValueError('Contact destination is already in use.')
        cursor.execute('UPDATE contact_changes SET consumed_at = CURRENT_TIMESTAMP WHERE user_id = %s AND consumed_at IS NULL', (user_id,))
        change_id, code = str(uuid.uuid4()), f'{secrets.randbelow(1000000):06d}'
        cursor.execute('''INSERT INTO contact_changes
            (change_id, user_id, contact_type, destination, code_hash, session_hash, password_id, preference, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP + INTERVAL '15 minutes')''',
            (change_id, user_id, kind, destination, generate_password_hash(code), session_hash, credential['password_id'], preference))
        log_audit(cursor, user_id, 'contact_change_requested', 'user', user_id, new_values=kind)
        conn.commit()
        return change_id, code, kind, destination


def finish_delivery(user_id, change_id, delivered):
    with closing(db_connect()) as conn, conn.cursor() as cursor:
        cursor.execute('''UPDATE contact_changes SET delivered_at = CASE WHEN %s THEN CURRENT_TIMESTAMP END,
            consumed_at = CASE WHEN %s THEN consumed_at ELSE CURRENT_TIMESTAMP END
            WHERE change_id = %s AND user_id = %s AND consumed_at IS NULL''', (delivered, delivered, change_id, user_id))
        if not delivered:
            log_audit(cursor, user_id, 'contact_change_delivery_failed', 'user', user_id)
        conn.commit()


def confirm_change(user_id, change_id, binding, code):
    session_hash = _session_hash(binding)
    with closing(db_connect()) as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        credential = _credential(cursor, user_id)
        cursor.execute('''SELECT *, expires_at > clock_timestamp() AS live FROM contact_changes
                          WHERE change_id = %s AND user_id = %s FOR UPDATE''', (change_id, user_id))
        pending = cursor.fetchone()
        valid = (pending and credential and pending['live'] and pending['consumed_at'] is None
                 and pending['delivered_at'] is not None and pending['attempt_count'] < MAX_ATTEMPTS
                 and pending['password_id'] == credential['password_id']
                 and secrets.compare_digest(pending['session_hash'], session_hash))
        if not valid or not isinstance(code, str) or len(code) != 6 or not check_password_hash(pending['code_hash'], code):
            if pending and pending['consumed_at'] is None:
                cursor.execute('UPDATE contact_changes SET attempt_count = attempt_count + 1 WHERE change_id = %s', (change_id,))
            log_audit(cursor, user_id, 'contact_change_rejected', 'user', user_id)
            conn.commit()
            raise ValueError('Invalid or expired contact code. Request a new code after five attempts.')
        cursor.execute('''SELECT contact_id, contact_value FROM contact WHERE user_id = %s AND contact_type = %s
                          ORDER BY is_primary DESC, contact_id DESC FOR UPDATE''', (user_id, pending['contact_type']))
        contacts = cursor.fetchall()
        previous = [row['contact_value'] for row in contacts if row['contact_value']]
        # All former destinations of this type lose recovery authority together.
        cursor.execute('''UPDATE password_reset SET is_used = TRUE WHERE contact_id IN
                          (SELECT contact_id FROM contact WHERE user_id = %s)''', (user_id,))
        if contacts:
            cursor.execute('''UPDATE contact SET contact_value = %s, verified_at = CURRENT_TIMESTAMP,
                              is_primary = (contact_id = %s) WHERE user_id = %s AND contact_type = %s''',
                           (pending['destination'], contacts[0]['contact_id'], user_id, pending['contact_type']))
        else:
            cursor.execute('''INSERT INTO contact (user_id, contact_type, contact_value, is_primary, created_at, verified_at)
                              VALUES (%s, %s, %s, TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)''',
                           (user_id, pending['contact_type'], pending['destination']))
        cursor.execute('UPDATE "user" SET preferred_contact = %s WHERE user_id = %s', (pending['preference'], user_id))
        cursor.execute('UPDATE contact_changes SET consumed_at = CURRENT_TIMESTAMP WHERE change_id = %s', (change_id,))
        log_audit(cursor, user_id, 'contact_change_confirmed', 'user', user_id, new_values=pending['contact_type'])
        conn.commit()
        return pending['contact_type'], previous


def notification_failed(user_id):
    with closing(db_connect()) as conn, conn.cursor() as cursor:
        log_audit(cursor, user_id, 'contact_change_notification_failed', 'user', user_id)
        conn.commit()
