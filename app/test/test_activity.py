from app.db.activity import record_capstone_activity_in_cursor


class ActivityCursor:
    def __init__(self, inserted=True, recipients=None):
        self.inserted = inserted
        self.recipients = recipients or []
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((" ".join(query.split()), params))

    def fetchone(self):
        if any("INSERT INTO capstone_activity" in query for query, _ in self.calls):
            return {"activity_id": 42} if self.inserted else None
        return None

    def fetchall(self):
        return [{"user_id": user_id} for user_id in self.recipients]


def test_activity_notifies_each_linked_author_without_actor_identity():
    cursor = ActivityCursor(recipients=[8, 9])

    assert record_capstone_activity_in_cursor(
        cursor, 17, 7, "view", event_variant="abstract"
    )

    notification_calls = [
        (query, params)
        for query, params in cursor.calls
        if "INSERT INTO notification" in query
    ]
    assert len(notification_calls) == 2
    assert {params[0] for _, params in notification_calls} == {8, 9}
    assert all("7" not in str(params[3:]) for _, params in notification_calls)


def test_duplicate_activity_does_not_notify_authors():
    cursor = ActivityCursor(inserted=False, recipients=[8])

    assert not record_capstone_activity_in_cursor(cursor, 17, 7, "citation")
    assert not any("SELECT DISTINCT a.user_id" in query for query, _ in cursor.calls)
