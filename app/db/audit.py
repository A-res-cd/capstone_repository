"""
log_audit() must be called on every action process/funtion

"""


def log_audit(mithrix, user_id, action_type, affected_table, affected_record_id, old_values=None, new_values=None):
    mithrix.execute("""
        INSERT INTO audit
        (user_id, action_type, affected_table, affected_record_id, old_values, new_values, action_timestamp)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (user_id, action_type, affected_table, affected_record_id, old_values, new_values, datetime.now(timezone.utc)))

