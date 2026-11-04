"""Durable at-least-once decision email delivery, only after signup commits."""
from contextlib import closing
import logging
from psycopg2.extras import RealDictCursor
from app.db.connection import db_connect
logger = logging.getLogger(__name__)

def deliver_pending(signup_id=None,limit=25):
    from app import mail
    from app.utils.account_emails import verification_email
    sent = 0
    for _ in range(max(0,min(limit,100))):
        with closing(db_connect()) as conn,conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''SELECT d.delivery_id,d.recipient_email,s.status,
                CONCAT_WS(' ',u.user_first_name,u.user_last_name) AS full_name
                FROM signup_decision_delivery d JOIN signup s USING(signup_id) JOIN "user" u USING(user_id)
                WHERE d.delivered_at IS NULL AND d.available_at<=CURRENT_TIMESTAMP
                AND (%s::int IS NULL OR d.signup_id=%s) ORDER BY d.delivery_id FOR UPDATE OF d SKIP LOCKED LIMIT 1''',(signup_id,signup_id))
            row = cursor.fetchone()
            if not row:
                break
            try:
                mail.send(verification_email({'email':row['recipient_email'],'full_name':row['full_name']},row['status'],
                    'Eligibility could not be confirmed. Contact your Capstone Professor to correct the master list, then verify your email and explicitly resubmit using your existing account.'))
            except Exception:
                logger.warning('Signup decision delivery failed; queued for retry (delivery %s)',row['delivery_id'])
                cursor.execute('''UPDATE signup_decision_delivery SET attempts=attempts+1,
                    available_at=CURRENT_TIMESTAMP+INTERVAL '15 minutes' WHERE delivery_id=%s''',(row['delivery_id'],))
            else:
                cursor.execute('''UPDATE signup_decision_delivery SET attempts=attempts+1,
                    delivered_at=CURRENT_TIMESTAMP WHERE delivery_id=%s''',(row['delivery_id'],))
                sent += 1
            conn.commit()
    return sent
