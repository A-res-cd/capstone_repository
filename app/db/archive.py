"""
Recycle Bin (soft-delete/restore/purge) and the public Explore
Archive browse/search — everything touching is_archived capstones.
"""
import logging
import psycopg2.extras
from datetime import datetime, timedelta, timezone

from app.db.connection import db_connect
from app.db.audit import log_audit

logger = logging.getLogger(__name__)

ARCHIVE_RETENTION_DAYS = 30


def get_archived_capstones(search=None, program_id=None, page=1, page_size=20):
    """
    Retrieve archived capstone projects for the admin archive management page.

    Supports:
        - Search by capstone title or keywords
        - Filter by program
        - Pagination

    Returns:
        (rows, total)
    """
    purge_expired_archived_capstones()

    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        conditions = ["c.is_archived = TRUE"]
        params = []

        # Search
        if search:
            conditions.append(
                "(c.capstone_title ILIKE %s OR k.capstone_keywords ILIKE %s)"
            )
            like = f"%{search}%"
            params += [like, like]

        # Program filter
        if program_id is not None:
            conditions.append("c.program_id = %s")
            params.append(program_id)

        where = "WHERE " + " AND ".join(conditions)

        # Get total count
        mithrix.execute(f"""
            SELECT COUNT(*) AS total
            FROM capstone c
            JOIN keyword k
                ON k.keyword_id = c.keyword_id
            JOIN specialization s
                ON s.specialization_id = c.specialization_id
            JOIN program p
                ON p.program_id = c.program_id
            {where}
        """, params)

        total = mithrix.fetchone()["total"]

        # Pagination
        offset = (page - 1) * page_size

        mithrix.execute(f"""
            SELECT
                c.capstone_id,
                c.capstone_title,
                c.capstone_year,
                c.capstone_file,
                c.citation_count,
                c.semester,
                c.term,
                k.keyword_id,
                k.capstone_keywords,
                s.specialization_id,
                s.specialization_name,
                p.program_id,
                p.program_name,
                c.archived_at
            FROM capstone c
            JOIN keyword k
                ON k.keyword_id = c.keyword_id
            JOIN specialization s
                ON s.specialization_id = c.specialization_id
            JOIN program p
                ON p.program_id = c.program_id
            {where}
            ORDER BY
                c.archived_at DESC NULLS LAST,
                c.capstone_year DESC,
                c.capstone_id DESC
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])

        rows = mithrix.fetchall()

        return list(rows), total

    except Exception as exc:
        logger.error("Database error: %s", exc)
        return [], 0

    finally:
        mithrix.close()
        conn.close()

def purge_expired_archived_capstones():
    """Delete archived capstones that have stayed in the recycle bin longer than 30 days."""
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cutoff = datetime.now(timezone.utc) - \
        timedelta(days=ARCHIVE_RETENTION_DAYS)

    try:
        mithrix.execute("""
            SELECT capstone_id
            FROM capstone
            WHERE is_archived = TRUE
              AND archived_at IS NOT NULL
              AND archived_at <= %s
        """, (cutoff,))

        expired_rows = mithrix.fetchall()
        deleted_count = 0

        for row in expired_rows:
            ok, _ = delete_capstone(row["capstone_id"], acting_user_id=None)
            if ok:
                deleted_count += 1

        return deleted_count
    except Exception as exc:
        logger.error("Error purging archived capstones: %s", exc)
        return 0
    finally:
        mithrix.close()
        conn.close()

def delete_capstone(capstone_id, acting_user_id=None):
    """
    Permanently delete an archived capstone project by ID, with cascading
    deletes for related records.

    acting_user_id is None when called from purge_expired_archived_capstones()
    (system-triggered, no admin in the loop) — log_audit accepts a NULL
    user_id for that case so the audit trail still records the deletion.

    Two admins can have the recycle bin open on the same item at once —
    one clicking Restore while the other clicks Delete. `SELECT ... FOR
    UPDATE` locks the row so whichever request gets there first wins
    outright; the second request blocks until the first commits, then
    re-reads the fresh state below and bails out with a clear message
    instead of silently deleting something that was just restored.
    """
    conn = db_connect()
    mithrix = conn.cursor()
    try:
        mithrix.execute("""
            SELECT keyword_id, is_archived, capstone_title FROM capstone
            WHERE capstone_id = %s
            FOR UPDATE
        """, (capstone_id,))
        row = mithrix.fetchone()
        if not row:
            conn.rollback()
            return False, "Capstone not found. It may have already been deleted by another admin."

        keyword_id, is_archived, capstone_title = row
        if not is_archived:
            conn.rollback()
            return False, "This capstone was just restored by another admin and can no longer be deleted from the recycle bin."

        # delete related capAuth entries first (authors/advisers)
        mithrix.execute("""
            DELETE FROM capAuth WHERE capstone_id = %s
        """, (capstone_id,))

        mithrix.execute("""
            DELETE FROM capstone WHERE capstone_id = %s
        """, (capstone_id,))

        # delete the keyword if no other capstone is using it
        mithrix.execute("""
            DELETE FROM keyword
            WHERE keyword_id = %s
              AND NOT EXISTS (
                  SELECT 1 FROM capstone WHERE keyword_id = %s
              )
        """, (keyword_id, keyword_id))

        log_audit(mithrix, acting_user_id, "delete_capstone", "capstone", capstone_id,
                   old_values=capstone_title)

        conn.commit()
        return True, "Capstone deleted successfully"
    except Exception as exc:
        conn.rollback()
        logger.error("Database error: %s", exc)
        return False, "A database error occurred. Please try again."
    finally:
        mithrix.close()
        conn.close()

def add_to_bin(capstone_id, acting_user_id=None):
    """
    Soft-delete (archive) a capstone into the recycle bin.

    Locks the row first so this can't race with another admin's concurrent
    action on the same capstone — see delete_capstone() for the full
    rationale.
    """
    conn = db_connect()
    mithrix = conn.cursor()
    now = datetime.now(timezone.utc)

    try:
        mithrix.execute("""
            SELECT is_archived FROM capstone
            WHERE capstone_id = %s
            FOR UPDATE
        """, (capstone_id,))
        row = mithrix.fetchone()
        if not row:
            conn.rollback()
            return False, "Capstone not found. It may have been deleted by another admin."

        if row[0]:
            conn.rollback()
            return False, "This capstone is already in the recycle bin."

        mithrix.execute("""
            UPDATE capstone
            SET is_archived = TRUE, archived_at = %s
            WHERE capstone_id = %s
        """, (now, capstone_id))

        log_audit(mithrix, acting_user_id, "archive_capstone", "capstone", capstone_id)

        conn.commit()
        return True, "Capstone moved to the recycle bin."
    except Exception as exc:
        conn.rollback()
        logger.error("Database error: %s", exc)
        return False, "A database error occurred. Please try again."
    finally:
        mithrix.close()
        conn.close()

def restore_capstone(capstone_id, acting_user_id=None):
    """
    Restore an archived capstone back to the live repository.

    Locks the row first so this can't race with another admin's concurrent
    permanent-delete (or restore) on the same capstone — see
    delete_capstone() for the full rationale.
    """
    conn = db_connect()
    mithrix = conn.cursor()

    try:
        mithrix.execute("""
            SELECT is_archived FROM capstone
            WHERE capstone_id = %s
            FOR UPDATE
        """, (capstone_id,))
        row = mithrix.fetchone()
        if not row:
            conn.rollback()
            return False, "Capstone not found. It may have been permanently deleted by another admin."

        if not row[0]:
            conn.rollback()
            return False, "This capstone was already restored, possibly by another admin."

        mithrix.execute("""
            UPDATE capstone
            SET is_archived = FALSE, archived_at = NULL
            WHERE capstone_id = %s
        """, (capstone_id,))

        log_audit(mithrix, acting_user_id, "restore_capstone", "capstone", capstone_id)

        conn.commit()
        return True, "Capstone restored to the repository."
    except Exception as exc:
        conn.rollback()
        logger.error("Database error: %s", exc)
        return False, "A database error occurred. Please try again."
    finally:
        mithrix.close()
        conn.close()


# ______________________________Explore Archive — public browse___________________________

def get_archive_capstones(search=None, year=None, page=1, page_size=12):
    """
    Fetch capstone records for the public archive list view.
    Joins keyword, specialization, and program for display.
    Returns (rows: list[RealDictRow], total: int).
    """
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        conditions = []
        params = []

        if search:
            conditions.append(
                "(c.capstone_title ILIKE %s OR k.capstone_keywords ILIKE %s)"
            )
            like = f"%{search}%"
            params += [like, like]

        if year:
            conditions.append("c.capstone_year = %s")
            params.append(year)

        where_clauses = ["is_archived = FALSE"]
        where_clauses.extend(conditions)

        where = "WHERE " + " AND ".join(where_clauses)

        # total count (same JOINs so filters apply)
        mithrix.execute(f"""
            SELECT COUNT(*) AS total
            FROM capstone c
            JOIN keyword k        ON k.keyword_id        = c.keyword_id
            JOIN specialization s ON s.specialization_id = c.specialization_id
            JOIN program p        ON p.program_id        = c.program_id
            {where}
        """, params)
        total = mithrix.fetchone()["total"]

        offset = (page - 1) * page_size

        mithrix.execute(f"""
            SELECT
                c.capstone_id,
                c.capstone_title,
                c.capstone_year,
                c.capstone_file,
                c.citation_count,
                c.semester,
                c.term,
                k.capstone_keywords,
                s.specialization_name,
                p.program_name
            FROM capstone c
            JOIN keyword k        ON k.keyword_id        = c.keyword_id
            JOIN specialization s ON s.specialization_id = c.specialization_id
            JOIN program p        ON p.program_id        = c.program_id
            {where}
            ORDER BY c.capstone_year DESC, c.capstone_title ASC
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])

        rows = mithrix.fetchall()
        return list(rows), total

    except Exception as exc:
        logger.error("Database error: %s", exc)
        return [], 0

    finally:
        mithrix.close()
        conn.close()

def get_archive_years():
    """Return distinct capstone_year values for the year filter dropdown."""
    conn = db_connect()
    mithrix = conn.cursor()
    try:
        mithrix.execute("""
            SELECT DISTINCT capstone_year
            FROM capstone
            WHERE capstone_year IS NOT NULL
            ORDER BY capstone_year DESC
        """)
        return [row[0] for row in mithrix.fetchall()]
    except Exception as exc:
        logger.error("Database error: %s", exc)
        return []
    finally:
        mithrix.close()
        conn.close()


# ______________________________Manage Users___________________________
