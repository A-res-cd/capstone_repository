"""Deduplicated manuscript submissions and most-requested capstone rankings."""
from contextlib import closing

import psycopg2.extras

from app.db.connection import db_connect

PERIOD_DAYS = {'all': None, '30d': 30, '7d': 7}
MAX_LIMIT = 50


def record_capstone_request(cursor, capstone_id, user_id=None):
    """Record in the caller's transaction; concurrent repeats count once per hour."""
    if user_id is not None:
        cursor.execute('SELECT pg_advisory_xact_lock(%s, %s)', (int(user_id), int(capstone_id)))
    cursor.execute("""
        WITH event_time AS (SELECT clock_timestamp() AS requested_at)
        INSERT INTO capstone_requests (capstone_id, user_id, requested_at)
        SELECT c.capstone_id, %s, event_time.requested_at
        FROM capstone c CROSS JOIN event_time
        WHERE c.capstone_id = %s AND c.is_archived = FALSE
          AND (%s IS NULL OR NOT EXISTS (
              SELECT 1 FROM capstone_requests previous
              WHERE previous.capstone_id = c.capstone_id AND previous.user_id = %s
                AND previous.requested_at > event_time.requested_at - INTERVAL '1 hour'
          ))
        RETURNING id
    """, (user_id, capstone_id, user_id, user_id))
    return cursor.fetchone() is not None


def get_most_requested_capstones(limit=5, period='all'):
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f'Limit must be an integer from 1 to {MAX_LIMIT}.')
    if period not in PERIOD_DAYS:
        raise ValueError('Period must be all, 30d, or 7d.')
    days = PERIOD_DAYS[period]
    date_filter = '' if days is None else "WHERE requested_at >= CURRENT_TIMESTAMP - (%s * INTERVAL '1 day')"
    params = [] if days is None else [days]
    params.append(limit)
    with closing(db_connect()) as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(f"""
            WITH counts AS (
                SELECT capstone_id, COUNT(*) AS request_count, MAX(requested_at) AS last_requested_at
                FROM capstone_requests
                {date_filter}
                GROUP BY capstone_id
            ), top_capstones AS (
                SELECT c.capstone_id, c.capstone_title, c.capstone_year, c.semester, c.term,
                       counts.request_count, counts.last_requested_at
                FROM counts JOIN capstone c ON c.capstone_id = counts.capstone_id
                WHERE c.is_archived = FALSE
                ORDER BY counts.request_count DESC, counts.last_requested_at DESC, c.capstone_id ASC
                LIMIT %s
            )
            SELECT c.capstone_id, c.capstone_title, c.capstone_year, c.semester, c.term,
                   c.request_count, c.last_requested_at,
                   COALESCE(team.authors, '') AS authors
            FROM top_capstones c
            LEFT JOIN LATERAL (
                SELECT STRING_AGG(CONCAT_WS(' ', NULLIF(a.aut_first_name, ''),
                    NULLIF(a.aut_middle_name, ''), NULLIF(a.aut_last_name, '')), ', '
                    ORDER BY ca.author_order NULLS LAST, a.author_id) AS authors
                FROM capauth ca JOIN author a ON a.author_id = ca.author_id
                WHERE ca.capstone_id = c.capstone_id AND ca.role = 'Author'
            ) team ON TRUE
            ORDER BY c.request_count DESC, c.last_requested_at DESC, c.capstone_id ASC
        """, params)
        return cursor.fetchall()


# Preserve the requested service spelling while following local Python naming.
getMostRequestedCapstones = get_most_requested_capstones
