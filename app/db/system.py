"""Durable maintenance state, job queue, and sanitized operational history."""
from contextlib import closing
from datetime import datetime, timezone

from psycopg2.extras import Json, RealDictCursor

from app.db.connection import db_connect
from app.db.role_security import guard_account_change


JOB_KINDS = {'diagnostics', 'backup', 'verify_backup', 'restore_test', 'cleanup', 'archive_purge', 'recovery_email'}


def _event(cur, actor, action, reason='', details=None, category='maintenance', severity='info', request_id=None):
    cur.execute('''INSERT INTO system_event(actor_id, category, severity, action, reason, details, request_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                (actor, category, severity, action[:100], reason[:500], Json(details or {}), request_id))


def record_event(action, **kwargs):
    with closing(db_connect()) as conn, conn:
        with conn.cursor() as cur:
            _event(cur, kwargs.pop('actor', None), action, **kwargs)


def settings():
    with closing(db_connect()) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT * FROM system_setting WHERE singleton = TRUE')
            row = cur.fetchone()
            if not row:
                raise RuntimeError('System settings migration is required')
            return row


def maintenance_active(state, now=None):
    now = now or datetime.now(timezone.utc)
    return bool(state['maintenance_enabled'] and
                (not state['maintenance_start'] or state['maintenance_start'] <= now) and
                (not state['maintenance_end'] or state['maintenance_end'] > now))


def save_settings(actor, reason, *, enabled=None, start=None, end=None, notice=None, interval=None, keep=None):
    with closing(db_connect()) as conn, conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT * FROM system_setting WHERE singleton = TRUE FOR UPDATE')
            if enabled is not None:
                cur.execute('''UPDATE system_setting SET maintenance_enabled=%s, maintenance_start=%s,
                               maintenance_end=%s, notice=%s WHERE singleton = TRUE''', (enabled, start, end, notice))
                _event(cur, actor, 'maintenance_changed', reason, {'enabled': enabled,
                       'start': start.isoformat() if start else None, 'end': end.isoformat() if end else None})
            else:
                cur.execute('UPDATE system_setting SET backup_interval_hours=%s, backup_keep=%s WHERE singleton=TRUE',
                            (interval, keep))
                _event(cur, actor, 'configuration_changed', reason, {'backup_interval_hours': interval, 'backup_keep': keep})


def enqueue(kind, actor, reason, payload=None):
    if kind not in JOB_KINDS:
        raise ValueError('Unknown maintenance job.')
    with closing(db_connect()) as conn, conn:
        with conn.cursor() as cur:
            cur.execute('''INSERT INTO maintenance_job(kind, actor_id, reason, payload) VALUES (%s,%s,%s,%s)
                           ON CONFLICT (kind) WHERE status IN ('queued','running') DO NOTHING RETURNING job_id''',
                        (kind, actor, reason, Json(payload or {})))
            row = cur.fetchone()
            if not row:
                raise ValueError('A job of this type is already queued or running.')
            _event(cur, actor, 'job_queued', reason, {'job_id': row[0], 'kind': kind})
            return row[0]


def jobs(limit=50):
    with closing(db_connect()) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT * FROM maintenance_job ORDER BY job_id DESC LIMIT %s', (limit,))
            return cur.fetchall()


def job(job_id):
    with closing(db_connect()) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT * FROM maintenance_job WHERE job_id=%s', (job_id,))
            return cur.fetchone()


def claim_job():
    with closing(db_connect()) as conn, conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('''UPDATE maintenance_job SET status='running', started_at=NOW()
                WHERE job_id=(SELECT job_id FROM maintenance_job WHERE status='queued'
                              ORDER BY job_id FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *''')
            return cur.fetchone()


def finish_job(job_id, result, failed=False):
    with closing(db_connect()) as conn, conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('''UPDATE maintenance_job SET status=%s, finished_at=NOW(), result=%s
                           WHERE job_id=%s RETURNING actor_id, kind''',
                        ('failed' if failed else 'succeeded', Json(result), job_id))
            row = cur.fetchone()
            _event(cur, row['actor_id'], 'job_failed' if failed else 'job_completed',
                   details={'job_id': job_id, 'kind': row['kind']}, severity='error' if failed else 'info')


def heartbeat():
    with closing(db_connect()) as conn, conn:
        with conn.cursor() as cur:
            cur.execute('UPDATE system_setting SET worker_seen_at=NOW() WHERE singleton=TRUE')


def recover_interrupted_jobs():
    with closing(db_connect()) as conn, conn:
        with conn.cursor() as cur:
            cur.execute('''UPDATE maintenance_job SET status='failed', finished_at=NOW(),
                           result='{"error":"Worker stopped before completion. Inspect before retrying."}'
                           WHERE status='running' ''')
            if cur.rowcount:
                _event(cur, None, 'worker_recovered', details={'interrupted_jobs': cur.rowcount}, severity='warning')


def due(kind, hours):
    with closing(db_connect()) as conn:
        with conn.cursor() as cur:
            cur.execute('''SELECT NOT EXISTS(SELECT 1 FROM maintenance_job WHERE kind=%s
                AND (status IN ('queued','running') OR created_at > NOW() - %s * INTERVAL '1 hour'))''', (kind, hours))
            return cur.fetchone()[0]


def events(category=None, severity=None, request_id=None, page=1, start=None, end=None):
    clauses, params = [], []
    for key, value in [('category', category), ('severity', severity), ('request_id', request_id)]:
        if value:
            clauses.append(f'{key}=%s')
            params.append(value)
    if start:
        clauses.append('created_at >= %s'); params.append(start)
    if end:
        clauses.append('created_at < %s'); params.append(end)
    where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
    with closing(db_connect()) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT * FROM system_event' + where + ' ORDER BY event_id DESC LIMIT 50 OFFSET %s',
                        params + [(page - 1) * 50])
            return cur.fetchall()


def security_accounts(search=''):
    with closing(db_connect()) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('''SELECT u.user_id, CONCAT_WS(' ',u.user_first_name,u.user_last_name) AS name,
                           r.role_name, u.account_status, u.locked_until FROM "user" u
                           JOIN role r ON r.role_id=u.role_id
                           WHERE CONCAT_WS(' ',u.user_first_name,u.user_last_name) ILIKE %s
                           ORDER BY u.user_id LIMIT 50''', ('%' + search + '%',))
            return cur.fetchall()


def secure_account(actor, user_id, action, reason):
    if actor == user_id:
        raise ValueError('Use My Account for your own security settings.')
    if action not in {'suspend', 'reactivate', 'unlock', 'revoke'}:
        raise ValueError('Unknown account action.')
    with closing(db_connect()) as conn, conn:
        target = guard_account_change(conn, user_id, academic=False, protect_last=action == 'suspend')
        with conn.cursor() as cur:
            if action == 'suspend':
                cur.execute('UPDATE "user" SET account_status=\'deactivated\' WHERE user_id=%s', (user_id,))
            elif action == 'unlock':
                cur.execute('UPDATE "user" SET locked_until=NULL WHERE user_id=%s', (user_id,))
            elif action == 'reactivate':
                if target['account_status'] != 'deactivated':
                    raise ValueError('Only a suspended account can be reactivated here. Academic verification belongs to RET Chair.')
                cur.execute('UPDATE "user" SET account_status=\'active\' WHERE user_id=%s', (user_id,))
            cur.execute('UPDATE "user" SET session_version=session_version+1 WHERE user_id=%s', (user_id,))
            _event(cur, actor, 'account_' + action, reason, {'user_id': user_id}, category='security')


def database_health():
    with closing(db_connect()) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SET statement_timeout='3s'")
            cur.execute('''SELECT pg_database_size(current_database()) AS size_bytes,
                           (SELECT count(*) FROM pg_stat_activity WHERE datname=current_database()) AS connections,
                           (SELECT count(*) FROM pg_stat_activity WHERE datname=current_database()
                            AND state='active' AND query_start < NOW()-INTERVAL '5 seconds') AS long_running,
                           current_setting('max_connections')::int AS max_connections''')
            return cur.fetchone()


def recovery_recipient(user_id):
    with closing(db_connect()) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('''SELECT k.username, c.contact_value AS email FROM "user" u
                           JOIN slug sl ON sl.user_id=u.user_id AND sl.is_current=TRUE
                           JOIN kappa k ON k.username_id=sl.username_id
                           JOIN contact c ON c.user_id=u.user_id AND c.contact_type='email' AND c.is_primary=TRUE
                           WHERE u.user_id=%s AND u.account_status IN ('active','deactivated') LIMIT 1''', (user_id,))
            return cur.fetchone()
