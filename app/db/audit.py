"""
Audit-trail logging. log_audit() is called from every other domain
module (auth, capstones, archive, users, requests) whenever a
state-changing action happens, so it lives on its own to avoid
circular imports.
"""
from datetime import datetime, timezone


def log_audit(mithrix, user_id, action_type, affected_table, affected_record_id, old_values=None, new_values=None):
    mithrix.execute("""
        INSERT INTO audit
        (user_id, action_type, affected_table, affected_record_id, old_values, new_values, action_timestamp)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (user_id, action_type, affected_table, affected_record_id, old_values, new_values, datetime.now(timezone.utc)))


