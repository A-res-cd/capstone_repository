"""Read storage keys that are still referenced by application records."""
from contextlib import closing

from app.db.connection import db_connect


def get_referenced_uploads():
    with closing(db_connect()) as conn, closing(conn.cursor()) as cursor:
        cursor.execute("""
            SELECT capstone_file FROM capstone WHERE capstone_file IS NOT NULL
            UNION ALL
            SELECT cor_filename FROM "user" WHERE cor_filename IS NOT NULL
            UNION ALL
            SELECT cor_filename FROM cor_registration
            WHERE cor_filename IS NOT NULL
            UNION ALL
            SELECT storage_key FROM user_avatar
        """)
        return [row[0] for row in cursor.fetchall()]
