"""Private verification-document reads. Call only from admin-protected routes."""
from psycopg2.extras import RealDictCursor
from app.db.connection import db_connect


STUDENT_REVIEW_SQL='''r.status IN ('pending','rejected') AND (r.status='pending' OR r.method='auto')
    AND u.account_status IN ('pending','rejected')
    AND NOT EXISTS (SELECT 1 FROM signup newer WHERE newer.user_id=r.user_id AND newer.signup_id>r.signup_id)
    AND NOT EXISTS (SELECT 1 FROM signup approved WHERE approved.user_id=r.user_id AND approved.status='approved')
    AND EXISTS (SELECT 1 FROM roster matched JOIN uploaded_by master USING(upload_id)
        WHERE matched.person_type='Student' AND master.status='active'
        AND UPPER(BTRIM(matched.university_no))=UPPER(BTRIM(u.university_no))
        AND (%s::int IS NULL OR master.uploader_user_id=%s))'''


def reviewer_owner(cursor,reviewer_id):
    from app.db.roster import _roster_owner
    return _roster_owner(cursor,reviewer_id)


def get_verification_details(request_id,reviewer_id=None):
    with db_connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        owner=reviewer_owner(cursor,reviewer_id) if reviewer_id is not None else None
        scope=f" AND (role.role_name<>'Student' OR ({STUDENT_REVIEW_SQL}))" if reviewer_id is not None else ''
        if reviewer_id is not None and owner is None:
            scope=f" AND (role.role_name<>'Student' OR COALESCE(r.status,u.account_status)='pending' OR ({STUDENT_REVIEW_SQL}))"
        cursor.execute(f'''
            SELECT r.signup_id AS request_id, r.user_id, r.status AS request_status, r.requested_at AS request_date,
                   CONCAT_WS(' ', u.user_first_name, u.user_middle_name, u.user_last_name) AS full_name,
                   u.university_no, role.role_name, u.account_status,
                   (SELECT k.username FROM slug sl JOIN kappa k ON k.username_id = sl.username_id
                    WHERE sl.user_id = u.user_id AND sl.is_current = TRUE ORDER BY sl.username_id DESC LIMIT 1) AS username,
                   (SELECT c.contact_value FROM contact c WHERE c.user_id = u.user_id
                    AND c.contact_type = 'email' AND c.is_primary = TRUE ORDER BY c.contact_id LIMIT 1) AS email,
                   u.cor_filename AS filename,r.reason AS verification_reason,
                   (role.role_name='Student') AS manual_student_review
            FROM signup r JOIN "user" u ON u.user_id = r.user_id
            JOIN role ON role.role_id = u.role_id
            WHERE r.signup_id = %s {scope}
        ''', (request_id,owner,owner) if reviewer_id is not None else (request_id,))
        return cursor.fetchone()


def get_verification_document(request_id,reviewer_id=None):
    if reviewer_id is not None:
        details=get_verification_details(request_id,reviewer_id)
        return {'filename':details['filename']} if details and details['filename'] else None
    with db_connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute('''SELECT u.cor_filename AS filename
            FROM "user" u JOIN signup r ON r.user_id = u.user_id
            WHERE r.signup_id = %s
              AND u.cor_filename IS NOT NULL
        ''', (request_id,))
        return cursor.fetchone()
