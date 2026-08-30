"""
Capstone repository CRUD: create/update/list/detail, keywords,
programs, specializations, authors/adviser assignment,
and the TF-IDF corpus feed for the topic-similarity recommender.
"""
import logging
import psycopg2.extras

from app.db.connection import db_connect
from app.db.audit import log_audit

logger = logging.getLogger(__name__)


def create_capstone_project(keyword_id, specialization_id, program_id,
                            capstone_title, capstone_year, capstone_file,
                            semester, term=None, acting_user_id=None,
                            is_utilized=False, is_presented=False, is_copyright_registered=False):
    conn = db_connect()
    mithrix = conn.cursor()
    try:
        mithrix.execute("""
            INSERT INTO capstone(keyword_id, specialization_id, program_id,
                        capstone_title, capstone_year, capstone_file,
                        semester, term,
                        is_utilized, is_presented, is_copyright_registered)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING capstone_id
        """, (keyword_id, specialization_id, program_id, capstone_title,
              capstone_year, capstone_file, semester, term,
              is_utilized, is_presented, is_copyright_registered))
        capstone_id = mithrix.fetchone()[0]

        log_audit(mithrix, acting_user_id, "create_capstone", "capstone", capstone_id,
                   new_values=capstone_title)

        conn.commit()
        return True, capstone_id
    except Exception as exc:
        conn.rollback()
        logger.error("Database error: %s", exc)
        return False, "A database error occurred. Please try again."
    finally:
        mithrix.close()
        conn.close()

def insert_keywords(capstone_keywords):
    conn = db_connect()
    mithrix = conn.cursor()
    try:
        mithrix.execute("""
            INSERT INTO keyword(capstone_keywords)
            VALUES (%s)
            RETURNING keyword_id
        """, (capstone_keywords,))
        keyword_id = mithrix.fetchone()[0]
        conn.commit()
        return True, keyword_id
    except Exception as exc:
        conn.rollback()
        logger.error("Database error: %s", exc)
        return False, "A database error occurred. Please try again."
    finally:
        mithrix.close()
        conn.close()

def get_programs():
    conn = db_connect()
    mithrix = conn.cursor()
    try:
        mithrix.execute("""SELECT program_id, program_name FROM program """)
        return mithrix.fetchall()
    except Exception as exc:
        logger.error("Database error: %s", exc)
        return []
    finally:
        mithrix.close()
        conn.close()

def get_specializations():
    conn = db_connect()
    mithrix = conn.cursor()
    try:
        mithrix.execute(
            """ SELECT specialization_id, specialization_name FROM specialization """)
        return mithrix.fetchall()
    except Exception as exc:
        logger.error("Database error: %s", exc)
        return []
    finally:
        mithrix.close()
        conn.close()

def get_used_keyword():
    conn = db_connect()
    mithrix = conn.cursor()
    try:
        mithrix.execute(""" SELECT DISTINCT k.keyword_id, k.capstone_keywords
                        FROM keyword k
                        INNER JOIN capstone c ON c.keyword_id = k.keyword_id
                        ORDER BY k.keyword_id """)
        return mithrix.fetchall()
    except Exception as exc:
        logger.error("Database error: %s", exc)
        return []
    finally:
        mithrix.close()
        conn.close()

def update_keyword(keyword_id, capstone_keywords):
    conn = db_connect()
    mithrix = conn.cursor()
    try:
        mithrix.execute("""
            UPDATE keyword
            SET capstone_keywords = %s
            WHERE keyword_id = %s
        """, (capstone_keywords, keyword_id))
        conn.commit()
        return True, None
    except Exception as exc:
        conn.rollback()
        logger.error("Database error: %s", exc)
        return False, "A database error occurred. Please try again."
    finally:
        mithrix.close()
        conn.close()

def get_capstone_details(capstone_id):
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        mithrix.execute("""
            SELECT c.capstone_id, c.capstone_title, c.capstone_year, c.capstone_file,
                   c.semester, c.term,
                   c.is_utilized, c.is_presented, c.is_copyright_registered,
                   k.keyword_id, k.capstone_keywords,
                   s.specialization_id, s.specialization_name,
                   p.program_id, p.program_name
            FROM capstone c
            JOIN keyword k ON c.keyword_id = k.keyword_id
            JOIN specialization s ON c.specialization_id = s.specialization_id
            JOIN program p ON c.program_id = p.program_id
            WHERE c.capstone_id = %s
        """, (capstone_id,))
        return mithrix.fetchone()
    except Exception as exc:
        logger.error("Database error: %s", exc)
        return None
    finally:
        mithrix.close()
        conn.close()

def update_capstone_record(capstone_id, keyword_id, specialization_id, program_id,
                           capstone_title, capstone_year, capstone_file,
                           semester, term=None, acting_user_id=None,
                           is_utilized=False, is_presented=False, is_copyright_registered=False):
    conn = db_connect()
    mithrix = conn.cursor()
    try:
        mithrix.execute("""
            UPDATE capstone
            SET keyword_id = %s,
                specialization_id = %s,
                program_id = %s,
                capstone_title = %s,
                capstone_year = %s,
                capstone_file = %s,
                semester = %s,
                term = %s,
                is_utilized = %s,
                is_presented = %s,
                is_copyright_registered = %s
            WHERE capstone_id = %s
        """, (keyword_id, specialization_id, program_id, capstone_title,
              capstone_year, capstone_file, semester, term,
              is_utilized, is_presented, is_copyright_registered, capstone_id))

        log_audit(mithrix, acting_user_id, "update_capstone", "capstone", capstone_id,
                   new_values=capstone_title)

        conn.commit()
        return True, None
    except Exception as exc:
        conn.rollback()
        logger.error("Database error: %s", exc)
        return False, "A database error occurred. Please try again."
    finally:
        mithrix.close()
        conn.close()

def get_all_capstones(search=None, program_id=None, page=1, page_size=20):
    """
    Retrieve capstone projects — search by title/keywords, filter by
    program, paginated. Returns (rows: list[RealDictRow], total: int).
    """
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        conditions = ["c.is_archived = FALSE"]
        params = []

        if search:
            conditions.append("(c.capstone_title ILIKE %s OR k.capstone_keywords ILIKE %s)")
            like = f"%{search}%"
            params += [like, like]

        if program_id:
            conditions.append("c.program_id = %s")
            params.append(program_id)

        where = "WHERE " + " AND ".join(conditions)

        mithrix.execute(f"""
            SELECT COUNT(*) AS total
            FROM capstone c
            JOIN keyword k ON c.keyword_id = k.keyword_id
            {where}
        """, params)
        total = mithrix.fetchone()["total"]

        offset = (page - 1) * page_size

        mithrix.execute(f"""
            SELECT c.capstone_id, c.capstone_title, c.capstone_year, c.capstone_file,
                   c.semester, c.term,
                   c.is_utilized, c.is_presented, c.is_copyright_registered,
                   k.keyword_id, k.capstone_keywords,
                   s.specialization_id, s.specialization_name,
                   p.program_id, p.program_name
            FROM capstone c
            JOIN keyword k ON c.keyword_id = k.keyword_id
            JOIN specialization s ON c.specialization_id = s.specialization_id
            JOIN program p ON c.program_id = p.program_id
            {where}
            ORDER BY c.capstone_year DESC, c.capstone_id DESC
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])

        return mithrix.fetchall(), total
    except Exception as exc:
        logger.error("Error: %s", exc)
        return [], 0
    finally:
        mithrix.close()
        conn.close()

def get_capstone_authors(casptone_id):
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        mithrix.execute("""
            SELECT a.aut_first_name, a.aut_middle_name, a.aut_last_name, ca.author_order
            FROM capAuth ca
            JOIN Author a On a.author_id = ca.author_id
            WHERE ca.capstone_id = %s AND ca.role = 'Author'
            ORDER BY ca.author_order ASC
        """, (casptone_id,))

        return mithrix.fetchall()
    
    except Exception as exc:
        logger.error("Database error: %s", exc)
        return[]
    
    finally:
        mithrix.close()
        conn.close()

def get_capstone_people(capstone_id):
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        mithrix.execute("""
            SELECT a.aut_first_name, a.aut_middle_name, a.aut_last_name, ca.author_order, ca.role
            FROM capAuth ca
            JOIN Author a ON a.author_id = ca.author_id
            WHERE ca.capstone_id = %s
            ORDER BY ca.author_order ASC
        """, (capstone_id, ))

        return mithrix.fetchall()

    except Exception as exc:
        logger.error("Database error: %s", exc)
        return []

    finally:
        conn.close()
        mithrix.close()

def set_capstone_people(capstone_id, authors, adviser, acting_user_id=None):
    conn = db_connect()
    mithrix = conn.cursor()

    try:
        mithrix.execute("""
            DELETE FROM capAuth WHERE capstone_id = %s
                        
        """, (capstone_id, ))

        order = 1
        for person in authors:
            first = (person.get("first") or "").strip()
            middle = (person.get("middle") or "").strip()
            last = (person.get("last") or "").strip()

            if not first and not last:
                continue

            mithrix.execute("""
                INSERT INTO Author (aut_first_name, aut_middle_name, aut_last_name)
                VALUES (%s, %s, %s)
                RETURNING author_id
            """, (first, middle or None, last))

            author_id = mithrix.fetchone()[0]

            mithrix.execute("""
                INSERT INTO capAuth (capstone_id, author_id, author_order, role)
                VALUES (%s, %s, %s, 'Author')
            """, (capstone_id, author_id, order))

            order += 1

        adv_first = (adviser.get("first") or "").strip()
        adv_middle = (adviser.get("middle") or "").strip()
        adv_last = (adviser.get("last") or "").strip()

        mithrix.execute("""
            INSERT INTO Author (aut_first_name, aut_middle_name, aut_last_name)
            VALUES (%s, %s, %s)
            RETURNING author_id
        """, (adv_first, adv_middle or None, adv_last))
        adviser_id = mithrix.fetchone()[0]

        mithrix.execute("""
            INSERT INTO capAuth (capstone_id, author_id, author_order, role)
            VALUES (%s, %s, %s, 'Adviser')
        """, (capstone_id, adviser_id, order))

        log_audit(mithrix, acting_user_id, "update_capstone_people", "capstone", capstone_id)

        conn.commit()
        return True, None
    except Exception as exc:
        conn.rollback()
        logger.error("Database error: %s", exc)
        return False, "A database error occurred. Please try again."
    finally:
        mithrix.close()
        conn.close()

def get_capstones_corpus():
    """
    Lightweight (capstone_id, title, keywords) list for every non-archived
    capstone — feeds the TF-IDF topic-similarity recommender. Kept as its
    own narrow query rather than reusing get_all_capstones() since the
    recommender only needs these three fields per record.
    """
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        mithrix.execute("""
            SELECT c.capstone_id, c.capstone_title, k.capstone_keywords
            FROM capstone c
            LEFT JOIN keyword k ON k.keyword_id = c.keyword_id
            WHERE c.is_archived IS NOT TRUE
        """)
        return mithrix.fetchall()
    except Exception as exc:
        logger.error("Database error: %s", exc)
        return []
    finally:
        mithrix.close()
        conn.close()
