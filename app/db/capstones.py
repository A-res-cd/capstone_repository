"""
Capstone repository CRUD: create/update/list/detail, keywords,
programs, specializations, authors/adviser assignment,
and the TF-IDF corpus feed for the topic-similarity recommender.
"""
import logging
import psycopg2.extras

from app.db.connection import db_connect
from app.db.audit import log_audit
from app.db.keywords import KEYWORD_JOIN, insert_keyword_ids, set_capstone_keywords

logger = logging.getLogger(__name__)


def create_capstone_project(keyword_id, specialization_id, program_id,
                            capstone_title, capstone_year, capstone_file,
                            semester, term=None, acting_user_id=None,
                            is_utilized=False, is_presented=False, is_copyright_registered=False, is_published=False, abstract_text=None,
                            capstone_keywords=None, authors=None, adviser=None):
    conn = db_connect()
    mithrix = conn.cursor()
    try:
        mithrix.execute("""
            INSERT INTO capstone(specialization_id, program_id,
                        capstone_title, capstone_year, capstone_file,
                        semester, term,
                        is_utilized, is_presented, is_copyright_registered, is_published, abstract_text)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING capstone_id
        """, (specialization_id, program_id, capstone_title,
              capstone_year, capstone_file, semester, term,
              is_utilized, is_presented, is_copyright_registered, is_published, abstract_text))
        capstone_id = mithrix.fetchone()[0]
        if capstone_keywords is not None:
            set_capstone_keywords(mithrix, capstone_id, capstone_keywords)
        elif keyword_id is not None:
            mithrix.execute("""
                INSERT INTO capstone_keyword (capstone_id, keyword_id) VALUES (%s, %s)
            """, (capstone_id, keyword_id))

        log_audit(mithrix, acting_user_id, "create_capstone", "capstone", capstone_id,
                   new_values=capstone_title)

        if authors is not None or adviser is not None:
            set_capstone_people(capstone_id, authors or [], adviser or {},
                                acting_user_id=acting_user_id, cursor=mithrix)

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
        keyword_ids = insert_keyword_ids(mithrix, capstone_keywords)
        conn.commit()
        return True, keyword_ids
    except Exception as exc:
        conn.rollback()
        logger.error("Database error: %s", exc)
        return False, "A database error occurred. Please try again."
    finally:
        mithrix.close()
        conn.close()

def get_programs(include_codes=False):
    conn = db_connect()
    mithrix = conn.cursor()
    try:
        mithrix.execute("SELECT program_id, program_name, program_code FROM program" if include_codes
                        else "SELECT program_id, program_name FROM program")
        return mithrix.fetchall()
    except Exception as exc:
        logger.error("Database error: %s", exc)
        return []
    finally:
        mithrix.close()
        conn.close()

def get_specializations(include_codes=False):
    conn = db_connect()
    mithrix = conn.cursor()
    try:
        mithrix.execute(
            "SELECT specialization_id, specialization_name, specialization_code FROM specialization" if include_codes
            else "SELECT specialization_id, specialization_name FROM specialization")
        return mithrix.fetchall()
    except Exception as exc:
        logger.error("Database error: %s", exc)
        return []
    finally:
        mithrix.close()
        conn.close()

def get_capstone_years():
    """Return years used by active repository records, newest first."""
    conn = db_connect()
    mithrix = conn.cursor()
    try:
        mithrix.execute("""
            SELECT DISTINCT capstone_year
            FROM capstone
            WHERE is_archived = FALSE AND capstone_year IS NOT NULL
            ORDER BY capstone_year DESC
        """)
        return [row[0] for row in mithrix.fetchall()]
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
        mithrix.execute(""" SELECT DISTINCT k.keyword_id, k.keyword_text AS capstone_keywords
                        FROM keyword k
                        INNER JOIN capstone_keyword ck ON ck.keyword_id = k.keyword_id
                        ORDER BY k.keyword_id """)
        return mithrix.fetchall()
    except Exception as exc:
        logger.error("Database error: %s", exc)
        return []
    finally:
        mithrix.close()
        conn.close()

def update_keyword(capstone_id, capstone_keywords):
    conn = db_connect()
    mithrix = conn.cursor()
    try:
        set_capstone_keywords(mithrix, capstone_id, capstone_keywords)
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
        mithrix.execute(f"""
            SELECT c.capstone_id, c.capstone_title, c.capstone_year, c.capstone_file,
                   c.semester, c.term,
                   c.is_published, c.abstract_text, c.is_utilized, c.is_presented, c.is_copyright_registered,
                   k.capstone_keywords,
                   s.specialization_id, s.specialization_name,
                   p.program_id, p.program_name
            FROM capstone c
            {KEYWORD_JOIN}
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
                           is_utilized=False, is_presented=False, is_copyright_registered=False, is_published=False, abstract_text=None,
                           capstone_keywords=None):
    conn = db_connect()
    mithrix = conn.cursor()
    try:
        mithrix.execute("""
            UPDATE capstone
            SET specialization_id = %s,
                program_id = %s,
                capstone_title = %s,
                capstone_year = %s,
                capstone_file = %s,
                semester = %s,
                term = %s,
                is_utilized = %s,
                is_presented = %s,
                is_copyright_registered = %s,
                is_published = %s,
                abstract_text = COALESCE(%s, abstract_text)
            WHERE capstone_id = %s
        """, (specialization_id, program_id, capstone_title,
              capstone_year, capstone_file, semester, term,
              is_utilized, is_presented, is_copyright_registered, is_published, abstract_text, capstone_id))

        if capstone_keywords is not None:
            set_capstone_keywords(mithrix, capstone_id, capstone_keywords)

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

def get_all_capstones(search=None, program_id=None, page=1, page_size=20,
                      search_scope="all", year=None, specialization_id=None):
    """
    Retrieve capstone projects — search by title/keywords/author (scoped to a
    single field via search_scope), filter by year, program, and specialization,
    paginated.
    Returns (rows: list[RealDictRow], total: int).
    """
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        conditions = ["c.is_archived = FALSE"]
        params = []

        if search and search_scope in {"title", "keyword"}:
            column = "c.capstone_title" if search_scope == "title" else "k.capstone_keywords"
            conditions.append(f"{column} ILIKE %s")
            params.append(f"%{search}%")
        elif search:
            conditions.append(
                """(
                    c.capstone_title ILIKE %s
                    OR k.capstone_keywords ILIKE %s
                    OR EXISTS (
                        SELECT 1
                        FROM capauth search_ca
                        JOIN author search_author
                          ON search_author.author_id = search_ca.author_id
                        WHERE search_ca.capstone_id = c.capstone_id
                          AND CONCAT_WS(' ', search_author.aut_first_name,
                                             search_author.aut_middle_name,
                                             search_author.aut_last_name) ILIKE %s
                    )
                )"""
            )
            like = f"%{search}%"
            params += [like, like, like]

        if program_id:
            conditions.append("c.program_id = %s")
            params.append(program_id)

        if year:
            conditions.append("c.capstone_year = %s")
            params.append(year)

        if specialization_id:
            conditions.append("c.specialization_id = %s")
            params.append(specialization_id)

        where = "WHERE " + " AND ".join(conditions)

        mithrix.execute(f"""
            SELECT COUNT(*) AS total
            FROM capstone c
            {KEYWORD_JOIN}
            {where}
        """, params)
        total = mithrix.fetchone()["total"]

        offset = (page - 1) * page_size

        mithrix.execute(f"""
            SELECT c.capstone_id, c.capstone_title, c.capstone_year, c.capstone_file,
                   c.semester, c.term,
                   c.is_published, c.abstract_text, c.is_utilized, c.is_presented, c.is_copyright_registered,
                   k.capstone_keywords,
                   s.specialization_id, s.specialization_name,
                   p.program_id, p.program_name
            FROM capstone c
            {KEYWORD_JOIN}
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

def set_capstone_people(capstone_id, authors, adviser, acting_user_id=None, cursor=None):
    conn = db_connect() if cursor is None else None
    mithrix = conn.cursor() if conn is not None else cursor

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

        if conn is not None:
            conn.commit()
        return True, None
    except Exception as exc:
        if conn is None:
            raise
        conn.rollback()
        logger.error("Database error: %s", exc)
        return False, "A database error occurred. Please try again."
    finally:
        if conn is not None:
            mithrix.close()
            conn.close()

def get_capstones_corpus():
    """
    Lightweight (capstone_id, title, keywords) list for every non-archived
    capstone, plus its specialization — feeds the TF-IDF topic-similarity
    recommender and topic-readiness panel. Kept as its own narrow query
    rather than reusing get_all_capstones().
    """
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        mithrix.execute(f"""
            SELECT c.capstone_id, c.capstone_title, c.abstract_text, k.capstone_keywords,
                   s.specialization_name
            FROM capstone c
            {KEYWORD_JOIN}
            LEFT JOIN specialization s ON s.specialization_id = c.specialization_id
            WHERE c.is_archived IS NOT TRUE
        """)
        return mithrix.fetchall()
    except Exception as exc:
        logger.error("Database error: %s", exc)
        return []
    finally:
        mithrix.close()
        conn.close()
