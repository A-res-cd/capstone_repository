"""Normalized COR records linked to user accounts."""
import psycopg2.extras

from app.db.connection import db_connect


def get_latest_cor_registration(user_id):
    conn = db_connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("""
                SELECT cor_registration_id, user_id, registration_no,
                       academic_year, term, year_level, cor_filename, uploaded_at
                FROM cor_registration
                WHERE user_id = %s
                ORDER BY uploaded_at DESC, cor_registration_id DESC
                LIMIT 1
            """, (user_id,))
            return cursor.fetchone()
    except Exception:
        return None
    finally:
        conn.close()


def insert_cor_registration(cursor, user_id, extracted, filename):
    """Insert or refresh one user's COR record inside an existing transaction."""
    registration_no = (extracted.get("registration_no") or "").strip()
    if not registration_no:
        return
    cursor.execute("""
        INSERT INTO cor_registration
            (user_id, registration_no, academic_year, term, year_level, cor_filename)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id, registration_no) DO UPDATE SET
            academic_year = EXCLUDED.academic_year,
            term = EXCLUDED.term,
            year_level = EXCLUDED.year_level,
            cor_filename = EXCLUDED.cor_filename,
            uploaded_at = CURRENT_TIMESTAMP
    """, (
        user_id,
        registration_no,
        extracted.get("academic_year") or None,
        extracted.get("term") or None,
        extracted.get("year_level") or None,
        filename,
    ))
