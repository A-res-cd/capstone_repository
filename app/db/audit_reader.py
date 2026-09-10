"""Read-only, paginated audit queries."""
from psycopg2.extras import RealDictCursor

from app.db.connection import db_connect
from app.utils.audit_summary import ACTION_GROUPS, summarize_audit


def get_audit_logs(filters, page=1):
    clauses, params = [], []
    for name, operator in [('start', '>='), ('end', '<')]:
        if filters.get(name):
            clauses.append(f'a.action_timestamp {operator} %s')
            params.append(filters[name])
    if filters.get('action'):
        clauses.append('a.action_type = %s')
        params.append(filters['action'])
    category = filters.get('category')
    known = [action for group in ACTION_GROUPS.values() for action in group]
    if category:
        if category == 'other':
            clauses.append('(a.action_type IS NULL OR NOT (a.action_type = ANY(%s)))')
            params.append(known)
        else:
            clauses.append('a.action_type = ANY(%s)')
            params.append(list(ACTION_GROUPS[category]))
    if filters.get('q'):
        # Treat wildcard characters literally, not as broad SQL patterns.
        query = filters['q'].replace('!', '!!').replace('%', '!%').replace('_', '!_')
        clauses.append("(CONCAT_WS(' ', u.user_first_name, u.user_middle_name, u.user_last_name) ILIKE %s ESCAPE '!' OR a.affected_record_id::text = %s OR a.audit_id::text = %s)")
        params.extend([f'%{query}%', filters['q'], filters['q']])
    source = ' FROM audit a LEFT JOIN "user" u ON u.user_id = a.user_id'
    where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
    with db_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Both reads share one snapshot, keeping totals and pages consistent.
            cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            cursor.execute('SELECT a.action_type, COUNT(*) AS total' + source + where + ' GROUP BY a.action_type', params)
            counts = dict.fromkeys(['account', 'capstone', 'workflow', 'other'], 0)
            for row in cursor.fetchall():
                key = next((key for key, group in ACTION_GROUPS.items() if row['action_type'] in group), 'other')
                counts[key] += row['total']
            total = sum(counts.values())
            pages = max(1, (total + 24) // 25)
            page = min(max(1, page), pages)
            cursor.execute('''SELECT a.*, CONCAT_WS(' ', u.user_first_name, u.user_middle_name, u.user_last_name) AS actor_name'''
                           + source + where + ' ORDER BY a.action_timestamp DESC NULLS LAST, a.audit_id DESC LIMIT %s OFFSET %s', params + [25, (page - 1) * 25])
            rows = cursor.fetchall()
            cursor.execute('SELECT role_id, role_name FROM role')
            roles = {row['role_id']: row['role_name'] for row in cursor.fetchall()}
    return {'events': [summarize_audit(row, roles) for row in rows], 'counts': counts,
            'total': total, 'page': page, 'pages': pages}
