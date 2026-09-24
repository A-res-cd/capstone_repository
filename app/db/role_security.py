"""Shared account boundaries and serialized last-operator protection."""
from psycopg2.extras import RealDictCursor

from app.constants.roles import ROLE_ADMIN, PRIVILEGED_ROLES, ACADEMIC_ROLES


def guard_account_change(conn, user_id, target_role_id=None, academic=True, protect_last=True):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtext('capre.role-guard'))")
        cur.execute('''SELECT u.role_id, u.account_status, r.role_name FROM "user" u
                       JOIN role r ON r.role_id = u.role_id WHERE u.user_id = %s FOR UPDATE OF u''', (user_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError("Account not found.")
        if academic and row['role_name'] == ROLE_ADMIN:
            raise ValueError("System Administrator accounts require privileged provisioning.")
        if target_role_id is not None:
            cur.execute('SELECT role_name FROM role WHERE role_id = %s', (target_role_id,))
            target = cur.fetchone()
            if not target or academic and target['role_name'] not in ACADEMIC_ROLES:
                raise ValueError("That role cannot be assigned here.")
        if protect_last and row['role_name'] in PRIVILEGED_ROLES and row['account_status'] == 'active':
            cur.execute('''SELECT COUNT(*) AS total FROM "user"
                           WHERE role_id = %s AND account_status = 'active' ''', (row['role_id'],))
            if cur.fetchone()['total'] <= 1:
                raise ValueError("Keep at least one active account for this privileged role.")
        return row


def require_requestable_role(cur, role_id):
    cur.execute('SELECT role_name FROM role WHERE role_id = %s', (role_id,))
    row = cur.fetchone()
    name = row['role_name'] if isinstance(row, dict) else row[0] if row else None
    if name not in ACADEMIC_ROLES or name in PRIVILEGED_ROLES:
        raise ValueError("Privileged roles cannot be requested as promotions.")
