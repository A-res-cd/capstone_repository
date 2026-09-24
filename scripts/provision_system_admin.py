"""Explicitly assign an existing active account to System Administrator."""
import argparse
from contextlib import closing
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.connection import db_connect
from app.db.role_security import guard_account_change
from app.db.system import _event


def provision(user_id, reason):
    with closing(db_connect()) as conn, conn:
        guard_account_change(conn, user_id, academic=False)
        with conn.cursor() as cur:
            cur.execute('''UPDATE "user" SET role_id=(SELECT role_id FROM role WHERE role_name='System Administrator')
                           WHERE user_id=%s AND account_status='active' RETURNING user_id''', (user_id,))
            if not cur.fetchone():
                raise ValueError('Only an existing active account may be provisioned.')
            _event(cur, user_id, 'system_admin_provisioned', reason, {'user_id': user_id, 'source': 'server CLI'}, category='security')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user-id', type=int, required=True)
    parser.add_argument('--reason', required=True)
    parser.add_argument('--confirm', required=True, choices=['PROVISION'])
    args = parser.parse_args()
    if len(args.reason.strip()) < 5 or len(args.reason) > 500:
        parser.error('Reason must be 5–500 characters.')
    provision(args.user_id, args.reason.strip())
    print('System Administrator provisioned. Existing sessions were revoked.')


if __name__ == '__main__':
    main()
