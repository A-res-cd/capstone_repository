"""Private verification-document reads. Call only from admin-protected routes."""
from psycopg2.extras import RealDictCursor
from app.db.connection import db_connect


def get_verification_details(request_id):
    with db_connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute('''
            SELECT r.request_id, r.user_id, r.request_status, r.request_date,
                   CONCAT_WS(' ', u.user_first_name, u.user_middle_name, u.user_last_name) AS full_name,
                   u.university_no, role.role_name, u.account_status,
                   (SELECT k.username FROM slug sl JOIN kappa k ON k.username_id = sl.username_id
                    WHERE sl.user_id = u.user_id AND sl.is_current = TRUE ORDER BY sl.username_id DESC LIMIT 1) AS username,
                   (SELECT c.contact_value FROM contact c WHERE c.user_id = u.user_id
                    AND c.contact_type = 'email' AND c.is_primary = TRUE ORDER BY c.contact_id LIMIT 1) AS email,
                   u.cor_filename AS filename
            FROM request r JOIN "user" u ON u.user_id = r.user_id
            JOIN role ON role.role_id = u.role_id
            WHERE r.request_id = %s AND r.request_type LIKE 'verification_%%'
        ''', (request_id,))
        return cursor.fetchone()


def get_verification_document(request_id):
    with db_connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute('''SELECT u.cor_filename AS filename
            FROM "user" u JOIN request r ON r.user_id = u.user_id
            WHERE r.request_id = %s AND r.request_type LIKE 'verification_%%'
              AND u.cor_filename IS NOT NULL
        ''', (request_id,))
        return cursor.fetchone()
