"""Short-lived, session-bound email ownership proof before account creation."""
from contextlib import closing
import secrets
import uuid

import psycopg2.extras
from werkzeug.security import generate_password_hash, check_password_hash
from app.db.connection import db_connect

EXPIRY_MINUTES = 15
MAX_ATTEMPTS = 5


def create_email_code(email, previous_id=None):
    email = email.strip().lower()
    code = f'{secrets.randbelow(1000000):06d}'
    verification_id = str(uuid.uuid4())
    with closing(db_connect()) as conn, conn.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext('signup-email'), hashtext(%s))", (email,))
        cursor.execute('DELETE FROM signup_email_verifications WHERE expires_at < CURRENT_TIMESTAMP')
        if previous_id:
            cursor.execute('UPDATE signup_email_verifications SET consumed_at = CURRENT_TIMESTAMP WHERE verification_id = %s AND consumed_at IS NULL', (previous_id,))
        cursor.execute("""
            INSERT INTO signup_email_verifications (verification_id, email, code_hash, expires_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP + (%s * INTERVAL '1 minute'))
        """, (verification_id, email, generate_password_hash(code), EXPIRY_MINUTES))
        conn.commit()
    return verification_id, code


def verify_email_code(verification_id, email, code):
    if not verification_id:
        return False
    with closing(db_connect()) as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute("""
            SELECT code_hash, attempts FROM signup_email_verifications
            WHERE verification_id = %s AND email = %s AND consumed_at IS NULL
              AND expires_at > clock_timestamp() FOR UPDATE
        """, (verification_id, email.strip().lower()))
        row = cursor.fetchone()
        if not row or row['attempts'] >= MAX_ATTEMPTS:
            return False
        if not check_password_hash(row['code_hash'], code):
            cursor.execute('UPDATE signup_email_verifications SET attempts = attempts + 1 WHERE verification_id = %s', (verification_id,))
            conn.commit()
            return False
        cursor.execute('UPDATE signup_email_verifications SET verified_at = CURRENT_TIMESTAMP WHERE verification_id = %s', (verification_id,))
        conn.commit()
    return True


def signup_email_is_verified(verification_id, email):
    if not verification_id:
        return False
    with closing(db_connect()) as conn, conn.cursor() as cursor:
        cursor.execute("""
            SELECT 1 FROM signup_email_verifications
            WHERE verification_id = %s AND email = %s AND verified_at IS NOT NULL
              AND consumed_at IS NULL AND expires_at > clock_timestamp()
        """, (verification_id, email.strip().lower()))
        return cursor.fetchone() is not None


def consume_email_verification(cursor, verification_id, email):
    cursor.execute("""
        UPDATE signup_email_verifications SET consumed_at = clock_timestamp()
        WHERE verification_id = %s AND email = %s AND verified_at IS NOT NULL
          AND consumed_at IS NULL AND expires_at > clock_timestamp()
        RETURNING verification_id
    """, (verification_id, email.strip().lower()))
    return cursor.fetchone() is not None
