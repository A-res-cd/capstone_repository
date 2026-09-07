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
            SELECT a.author_id, a.user_id, a.aut_first_name, a.aut_middle_name,
                   a.aut_last_name, ca.author_order, ca.role
            FROM capAuth ca
            JOIN Author a ON a.author_id = ca.author_id
            WHERE ca.capstone_id = %s
            ORDER BY ca.author_order ASC
        """, (capstone_id, ))

        return mithrix.fetchall()

    except Exception as exc:
        logger.error("Database error: %s", exc)
        raise

    finally:
        conn.close()
        mithrix.close()

def set_capstone_people(capstone_id, authors, adviser, acting_user_id=None):
    conn = db_connect()
    mithrix = conn.cursor()

    try:
        # Serialize edits and only accept author IDs already attached here.
        mithrix.execute("SELECT capstone_id FROM capstone WHERE capstone_id = %s FOR UPDATE", (capstone_id,))
        if not mithrix.fetchone():
            raise ValueError("Capstone not found.")
        mithrix.execute("""
            SELECT a.author_id, a.aut_first_name, a.aut_middle_name,
                   a.aut_last_name, a.user_id, ca.role,
                   EXISTS (SELECT 1 FROM capAuth other
                           WHERE other.author_id = a.author_id AND other.capstone_id <> %s)
            FROM capAuth ca JOIN Author a ON a.author_id = ca.author_id
            WHERE ca.capstone_id = %s
            ORDER BY a.author_id
            FOR UPDATE OF a, ca
        """, (capstone_id, capstone_id))
        existing = {row[0]: row for row in mithrix.fetchall()}
        kept_ids, seen_ids, seen_users = [], set(), set()

        for person, role in [(person, "Author") for person in authors] + [(adviser, "Adviser")]:
            first = (person.get("first") or "").strip()
            middle = (person.get("middle") or "").strip()
            last = (person.get("last") or "").strip()
            author_id = int(person.get("author_id") or 0)
            if author_id and (author_id not in existing or existing[author_id][5] != role):
                raise ValueError("Author details changed. Reload the capstone and try again.")
            if author_id and author_id in seen_ids:
                raise ValueError("An author cannot appear twice in the same capstone.")
            seen_ids.add(author_id)
            previous = existing.get(author_id)
            user_id = (int(person.get("user_id") or 0) or None) if role == "Author" else None
            if role == "Author" and "user_id" not in person and previous:
                user_id = previous[4]
            if previous and previous[4] and user_id and previous[4] != user_id:
                raise ValueError("Unlink the existing account before assigning a different one.")
            if not first and not last:
                if user_id:
                    raise ValueError("Enter the author name before linking an account.")
                continue
            if user_id:
                if user_id in seen_users:
                    raise ValueError("Link each account to only one author per capstone.")
                seen_users.add(user_id)
                mithrix.execute('SELECT user_id FROM "user" WHERE user_id = %s FOR KEY SHARE', (user_id,))
                if not mithrix.fetchone():
                    raise ValueError("Selected author account no longer exists.")
                if not previous or previous[4] != user_id:
                    if acting_user_id == user_id:
                        raise ValueError("Another capstone professor must verify your own author credit.")
                    mithrix.execute('''
                        SELECT 1 FROM "user" u WHERE u.user_id = %s AND u.account_status = 'active'
                          AND EXISTS (SELECT 1 FROM request r WHERE r.user_id = u.user_id
                                      AND r.request_type = 'capstoner' AND r.request_status = 'approved')
                    ''', (user_id,))
                    if not mithrix.fetchone():
                        raise ValueError("A capstone professor must approve this capstoner first.")

            values = (first, middle or None, last, user_id)
            # Legacy records may be shared. Change only this capstone's credit,
            # never another work's name/account assignment as a side effect.
            if not previous or (previous[6] and tuple(previous[1:5]) != values):
                mithrix.execute("""
                    INSERT INTO Author (aut_first_name, aut_middle_name, aut_last_name, user_id)
                    VALUES (%s, %s, %s, %s) RETURNING author_id
                """, values)
                author_id = mithrix.fetchone()[0]
            elif tuple(previous[1:5]) != values:
                mithrix.execute("""
                    UPDATE Author SET aut_first_name = %s, aut_middle_name = %s,
                                      aut_last_name = %s, user_id = %s
                    WHERE author_id = %s
                """, values + (author_id,))
            mithrix.execute("""
                INSERT INTO capAuth (capstone_id, author_id, author_order, role)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (capstone_id, author_id) DO UPDATE
                    SET author_order = EXCLUDED.author_order, role = EXCLUDED.role
            """, (capstone_id, author_id, len(kept_ids) + 1, role))
            kept_ids.append(author_id)

        mithrix.execute("""
            DELETE FROM capAuth WHERE capstone_id = %s AND NOT (author_id = ANY(%s))
        """, (capstone_id, kept_ids))

        log_audit(mithrix, acting_user_id, "update_capstone_people", "capstone", capstone_id)

        conn.commit()
        return True, None
    except ValueError as exc:
        conn.rollback()
        return False, str(exc)
    except Exception as exc:
        conn.rollback()
        logger.error("Database error: %s", exc)
        return False, "A database error occurred. Please try again."
    finally:
        mithrix.close()
        conn.close()

def get_author_account_choices():
    """Approved capstoners; retain existing links for non-destructive edits."""
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        mithrix.execute('''
            SELECT u.user_id, u.user_first_name, u.user_middle_name, u.user_last_name, u.university_no
            FROM "user" u
            WHERE EXISTS (SELECT 1 FROM request r WHERE r.user_id = u.user_id
                          AND r.request_type = 'capstoner' AND r.request_status = 'approved')
               OR EXISTS (SELECT 1 FROM author a WHERE a.user_id = u.user_id)
            ORDER BY u.user_last_name, u.user_first_name, u.user_id
        ''')
        return mithrix.fetchall()
    finally:
        mithrix.close()
        conn.close()


def get_user_authored_capstones(user_id):
    """Account-linked author credits only; duplicate credits count as one work."""
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        mithrix.execute("""
            SELECT c.capstone_id, c.capstone_title AS title, c.capstone_year AS year,
                   COALESCE(s.specialization_name, 'Not specified') AS specialization,
                   'Author' AS role, 'Published' AS status
            FROM capstone c
            LEFT JOIN specialization s ON s.specialization_id = c.specialization_id
            WHERE c.is_archived IS NOT TRUE AND EXISTS (
                SELECT 1 FROM capAuth ca JOIN Author a ON a.author_id = ca.author_id
                WHERE ca.capstone_id = c.capstone_id AND ca.role = 'Author' AND a.user_id = %s
            )
            ORDER BY c.capstone_year DESC NULLS LAST, c.capstone_title, c.capstone_id
        """, (user_id,))
        return mithrix.fetchall()
    finally:
        mithrix.close()
        conn.close()


def get_capstones_corpus():
    """
    Lightweight (capstone_id, title) list for every non-archived
    capstone, plus its specialization — feeds the title-similarity
    recommender and topic-readiness panel. Kept as its own narrow query
    rather than reusing get_all_capstones().
    """
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        mithrix.execute("""
            SELECT c.capstone_id, c.capstone_title,
                   s.specialization_name
            FROM capstone c
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
