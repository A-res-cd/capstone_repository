"""Review history shares the existing request decision records."""
import psycopg2.extras
from app.db.connection import db_connect


def get_review_history(page=1, recent=False, verification_only=False, reviewed_by=None):
    size = 5 if recent else 20
    conn = db_connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            condition = "r.decision_date IS NOT NULL AND r.request_status IN ('approved', 'rejected')"
            params = []
            if verification_only:
                condition += " AND r.request_type LIKE 'verification_%%'"
            if reviewed_by is not None:
                condition += " AND r.reviewed_by = %s"
                params.append(reviewed_by)
            cursor.execute('SELECT COUNT(*) AS total FROM request r WHERE ' + condition, params)
            total = cursor.fetchone()['total']
            cursor.execute('''SELECT r.request_id, r.request_type, r.request_status,
                r.status_reason, r.decision_date, c.capstone_title,
                CONCAT_WS(' ', u.user_first_name, u.user_last_name) AS requester,
                CONCAT_WS(' ', reviewer.user_first_name, reviewer.user_last_name) AS reviewer
                FROM request r LEFT JOIN "user" u ON u.user_id = r.user_id
                LEFT JOIN "user" reviewer ON reviewer.user_id = r.reviewed_by
                LEFT JOIN capstone c ON c.capstone_id = r.capstone_id
                WHERE ''' + condition + ''' ORDER BY r.decision_date DESC, r.request_id DESC
                LIMIT %s OFFSET %s''', params + [size, (page - 1) * size])
            return cursor.fetchall(), total, size
    finally:
        conn.close()
