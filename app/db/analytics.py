"""
Read-only aggregate queries for the Analytics & Reports dashboard —
per-program/specialization breakdowns, trend-over-time, status-flag
donuts (Utilized/Presented/Copyright Registered), and top-cited list.
"""
import logging
import psycopg2.extras

from app.db.connection import db_connect

logger = logging.getLogger(__name__)
_QUERY_ERROR = "Analytics data is temporarily unavailable."


def get_capstones_by_program():
    """Capstone count grouped by program — mirrors the reference dashboard's
    per-program stat cards and program donut chart."""
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        mithrix.execute("""
            SELECT p.program_id, p.program_name, COUNT(c.capstone_id) AS total
            FROM program p
            LEFT JOIN capstone c ON c.program_id = p.program_id AND c.is_archived IS NOT TRUE
            GROUP BY p.program_id, p.program_name
            ORDER BY total DESC
        """)
        return mithrix.fetchall(), None
    except Exception as exc:
        logger.error("Analytics query failed: %s", exc)
        return [], _QUERY_ERROR
    finally:
        mithrix.close()
        conn.close()

def get_capstone_program_summary():
    """
    Per-program breakdown for the Analytics 'Summary by Program' table:
    total, published (= total, every archived record is a published
    entry), utilized, presented, copyright-registered counts. Mirrors
    the reference dashboard's summary table.
    """
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        mithrix.execute("""
            SELECT p.program_id, p.program_name,
                   COUNT(c.capstone_id) AS total,
                   COUNT(c.capstone_id) FILTER (WHERE c.is_utilized) AS utilized,
                   COUNT(c.capstone_id) FILTER (WHERE c.is_presented) AS presented,
                   COUNT(c.capstone_id) FILTER (WHERE c.is_copyright_registered) AS copyright_registered
            FROM program p
            LEFT JOIN capstone c ON c.program_id = p.program_id AND c.is_archived IS NOT TRUE
            GROUP BY p.program_id, p.program_name
            ORDER BY total DESC
        """)
        return mithrix.fetchall(), None
    except Exception as exc:
        logger.error("Analytics query failed: %s", exc)
        return [], _QUERY_ERROR
    finally:
        mithrix.close()
        conn.close()

def get_capstone_trend_by_specialization():
    """
    Capstone count per specialization per academic year — feeds the
    multi-line 'Capstone Trend per Year' chart. Returns (years, {specialization_name: [counts...]})
    with years ascending and each specialization's list aligned to that
    year list (0 where a specialization had no capstones that year).
    """
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        mithrix.execute("""
            SELECT c.capstone_year, s.specialization_name, COUNT(c.capstone_id) AS total
            FROM capstone c
            JOIN specialization s ON s.specialization_id = c.specialization_id
            WHERE c.capstone_year IS NOT NULL AND c.is_archived IS NOT TRUE
            GROUP BY c.capstone_year, s.specialization_name
            ORDER BY c.capstone_year ASC
        """)
        rows = mithrix.fetchall()

        years = sorted({row["capstone_year"] for row in rows})
        specializations = sorted({row["specialization_name"] for row in rows})

        lookup = {(row["capstone_year"], row["specialization_name"]): row["total"] for row in rows}
        series = {
            specialization: [lookup.get((year, specialization), 0) for year in years]
            for specialization in specializations
        }

        return years, series, None
    except Exception as exc:
        logger.error("Analytics query failed: %s", exc)
        return [], {}, _QUERY_ERROR
    finally:
        mithrix.close()
        conn.close()

def get_capstones_by_specialization():
    """Capstone count grouped by specialization — for the Analytics bar chart."""
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        mithrix.execute("""
            SELECT s.specialization_name, COUNT(c.capstone_id) AS total
            FROM capstone c
            JOIN specialization s ON s.specialization_id = c.specialization_id
            GROUP BY s.specialization_name
            ORDER BY total DESC
        """)
        return mithrix.fetchall(), None
    except Exception as exc:
        logger.error("Analytics query failed: %s", exc)
        return [], _QUERY_ERROR
    finally:
        mithrix.close()
        conn.close()

def get_capstone_status_flags():
    """
    Counts capstones flagged Utilized / Presented / Copyright Registered
    (vs not) among non-archived capstones — feeds the three small
    Analytics donuts. Previously excluded per SESSION_HANDOFF.md #9
    since no tracking columns existed; capstone.is_utilized /
    is_presented / is_copyright_registered now provide that.
    """
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        mithrix.execute("""
            SELECT
                COUNT(*) FILTER (WHERE is_utilized) AS utilized,
                COUNT(*) FILTER (WHERE NOT is_utilized) AS not_utilized,
                COUNT(*) FILTER (WHERE is_presented) AS presented,
                COUNT(*) FILTER (WHERE NOT is_presented) AS not_presented,
                COUNT(*) FILTER (WHERE is_copyright_registered) AS copyright_registered,
                COUNT(*) FILTER (WHERE NOT is_copyright_registered) AS not_copyright_registered
            FROM capstone
            WHERE is_archived IS NOT TRUE
        """)
        return mithrix.fetchone(), None
    except Exception as exc:
        logger.error("Analytics query failed: %s", exc)
        return None, _QUERY_ERROR
    finally:
        mithrix.close()
        conn.close()

# FAHHHHH ANG DAMI FUNCTIONSSSSSSSS IM SICK AND TIRED OF THISSSSSSS
