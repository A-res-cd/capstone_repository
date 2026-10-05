"""Each student keeps their own most recently viewed capstones."""
import logging
import psycopg2.extras
from app.db.connection import db_connect

logger = logging.getLogger(__name__)


def record_capstone_view(user_id, capstone_id):
    conn = db_connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute('''INSERT INTO capstone_view_history (user_id, capstone_id)
                SELECT %s, capstone_id FROM capstone
                WHERE capstone_id = %s AND is_archived IS NOT TRUE
                ON CONFLICT (user_id, capstone_id)
                DO UPDATE SET viewed_at = CURRENT_TIMESTAMP''', (user_id, capstone_id))
            recorded = cursor.rowcount == 1
        conn.commit()
        return recorded
    except Exception:
        conn.rollback()
        logger.exception('Could not save viewing history')
        return False
    finally:
        conn.close()


def get_view_history(user_id, page=1, page_size=20):
    conn = db_connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute('''SELECT COUNT(*) AS total
                FROM capstone_view_history h JOIN capstone c USING (capstone_id)
                WHERE h.user_id = %s AND c.is_archived IS NOT TRUE''', (user_id,))
            total = cursor.fetchone()['total']
            cursor.execute('''SELECT c.capstone_id, c.capstone_title, c.capstone_year,
                p.program_code, p.program_name, s.specialization_code, s.specialization_name,
                h.viewed_at
                FROM capstone_view_history h JOIN capstone c USING (capstone_id)
                LEFT JOIN program p USING (program_id)
                LEFT JOIN specialization s USING (specialization_id)
                WHERE h.user_id = %s AND c.is_archived IS NOT TRUE
                ORDER BY h.viewed_at DESC, h.capstone_id DESC LIMIT %s OFFSET %s''',
                (user_id, page_size, (page - 1) * page_size))
            return cursor.fetchall(), total
    finally:
        conn.close()
