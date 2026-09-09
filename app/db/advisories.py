"""Explicit advisory rosters; membership grants no authorship or approval."""
import logging

import psycopg2.extras

from app.db.audit import log_audit
from app.db.connection import db_connect

logger = logging.getLogger(__name__)
MAX_ADVISORY_GROUP_STUDENTS = 4


def _require_professor(cursor, professor_id, *, lock=False):
    cursor.execute('''
        SELECT user_id FROM "user"
        WHERE user_id = %s AND role_id = 4 AND account_status = 'active'
    ''' + (" FOR NO KEY UPDATE" if lock else ""), (professor_id,))
    if not cursor.fetchone():
        raise PermissionError("Only an active capstone professor can manage an advisory roster.")


def get_advisory_groups(professor_id):
    conn = db_connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            _require_professor(cursor, professor_id)
            cursor.execute("""
                SELECT g.group_id, g.group_name, COUNT(s.student_user_id)::INT AS student_count
                FROM advisory_group g LEFT JOIN advisory_student s
                  ON s.professor_user_id = g.professor_user_id AND s.group_id = g.group_id
                WHERE g.professor_user_id = %s
                GROUP BY g.group_id ORDER BY g.created_at, g.group_id
            """, (professor_id,))
            return cursor.fetchall()
    finally:
        conn.close()


def _change_group(professor_id, name, *, group_id=None):
    name = (name or "").strip()
    if not name or len(name) > 100:
        return False, "Enter a group name between 1 and 100 characters."
    conn = db_connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            _require_professor(cursor, professor_id, lock=True)
            old_name = None
            if group_id is None:
                cursor.execute("""
                    INSERT INTO advisory_group (professor_user_id, group_name)
                    VALUES (%s, %s) RETURNING group_id
                """, (professor_id, name))
                group_id = cursor.fetchone()["group_id"]
                action = "create_advisory_group"
            else:
                cursor.execute("""
                    SELECT group_name FROM advisory_group
                    WHERE group_id = %s AND professor_user_id = %s FOR UPDATE
                """, (group_id, professor_id))
                group = cursor.fetchone()
                if not group:
                    raise ValueError("This group is not on your advisory roster.")
                old_name = group["group_name"]
                cursor.execute("""
                    UPDATE advisory_group SET group_name = %s
                    WHERE group_id = %s AND professor_user_id = %s
                """, (name, group_id, professor_id))
                action = "rename_advisory_group"
            log_audit(cursor, professor_id, action, "advisory_group", group_id,
                      old_values=old_name, new_values=name)
        conn.commit()
        return True, None
    except (ValueError, PermissionError) as exc:
        conn.rollback()
        return False, str(exc)
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return False, "You already have a group with that name. Choose a different name."
    except Exception as exc:
        conn.rollback()
        logger.error("Advisory group database error: %s", exc)
        return False, "Could not save your advisory group. Please try again."
    finally:
        conn.close()


def create_advisory_group(professor_id, name):
    return _change_group(professor_id, name)


def _add_students_in_cursor(cursor, professor_id, student_ids, group_id):
    if not student_ids or len(student_ids) != len(set(student_ids)):
        raise ValueError("Select at least one student, with no duplicate accounts.")
    if len(student_ids) > MAX_ADVISORY_GROUP_STUDENTS:
        raise ValueError(f"Groups can have at most {MAX_ADVISORY_GROUP_STUDENTS} students.")

    cursor.execute('''
        SELECT user_id, role_id, account_status FROM "user"
        WHERE user_id = ANY(%s) ORDER BY user_id FOR NO KEY UPDATE
    ''', ([professor_id, *student_ids],))
    users = {row["user_id"]: row for row in cursor.fetchall()}
    professor = users.get(professor_id)
    if not professor or professor["role_id"] != 4 or professor["account_status"] != "active":
        raise ValueError("Only an active capstone professor can manage an advisory roster.")
    if professor_id in student_ids:
        raise ValueError("You cannot add yourself as an advisory student.")

    cursor.execute("""
        SELECT group_id FROM advisory_group
        WHERE group_id = %s AND professor_user_id = %s
    """, (group_id, professor_id))
    if not cursor.fetchone():
        raise ValueError("Create a group first, then choose one of your advisory groups.")

    for student_id in student_ids:
        student = users.get(student_id)
        if not student or student["role_id"] != 1 or student["account_status"] != "active":
            raise ValueError("Choose active, verified student accounts. No students were added.")

    cursor.execute("""
        SELECT COUNT(*) AS student_count FROM advisory_student
        WHERE professor_user_id = %s AND group_id = %s
    """, (professor_id, group_id))
    if cursor.fetchone()["student_count"] + len(student_ids) > MAX_ADVISORY_GROUP_STUDENTS:
        raise ValueError(f"Groups can have at most {MAX_ADVISORY_GROUP_STUDENTS} students. Create another group or remove a student first.")

    for student_id in student_ids:
        cursor.execute("""
            INSERT INTO advisory_student (professor_user_id, student_user_id, group_id)
            VALUES (%s, %s, %s) ON CONFLICT DO NOTHING RETURNING student_user_id
        """, (professor_id, student_id, group_id))
        if not cursor.fetchone():
            raise ValueError("A selected student is already on your advisory roster. No students were added.")
        log_audit(cursor, professor_id, "add_advisory_student", "advisory_student", student_id,
                  new_values=f"professor_user_id={professor_id}; student_user_id={student_id}; group_id={group_id}")


def create_advisory_group_with_students(professor_id, name, student_ids):
    name = (name or "").strip()
    if not name or len(name) > 100:
        return False, "Enter a group name between 1 and 100 characters."
    conn = db_connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            _require_professor(cursor, professor_id, lock=True)
            cursor.execute("""
                INSERT INTO advisory_group (professor_user_id, group_name)
                VALUES (%s, %s) RETURNING group_id
            """, (professor_id, name))
            group_id = cursor.fetchone()["group_id"]
            log_audit(cursor, professor_id, "create_advisory_group", "advisory_group", group_id,
                      new_values=name)
            if student_ids:
                _add_students_in_cursor(cursor, professor_id, student_ids, group_id)
        conn.commit()
        return True, None
    except (ValueError, PermissionError) as exc:
        conn.rollback()
        return False, str(exc)
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return False, "You already have a group with that name. Choose a different name."
    except Exception as exc:
        conn.rollback()
        logger.error("Advisory group database error: %s", exc)
        return False, "Could not create your advisory group. Please try again."
    finally:
        conn.close()


def rename_advisory_group(professor_id, group_id, name):
    if group_id is None:
        return False, "Choose one of your advisory groups to rename."
    return _change_group(professor_id, name, group_id=group_id)


def get_advisory_roster(professor_id):
    conn = db_connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            _require_professor(cursor, professor_id)
            cursor.execute("""
                SELECT u.user_id, u.user_first_name, u.user_last_name,
                       CONCAT_WS(' ', u.user_first_name, u.user_middle_name, u.user_last_name) AS full_name,
                       u.university_no, u.account_status, r.added_at, r.group_id,
                       COALESCE(reg.request_status, 'unregistered') AS capstoner_status
                FROM advisory_student r JOIN "user" u ON u.user_id = r.student_user_id
                LEFT JOIN LATERAL (
                    SELECT request_status FROM request
                    WHERE user_id = u.user_id AND request_type = 'capstoner'
                    ORDER BY request_id DESC LIMIT 1
                ) reg ON TRUE
                WHERE r.professor_user_id = %s
                ORDER BY u.user_last_name, u.user_first_name, u.user_id
            """, (professor_id,))
            students = cursor.fetchall()
            by_id = {student["user_id"]: student for student in students}
            for student in students:
                student["works"] = []
            cursor.execute("""
                SELECT DISTINCT a.user_id, c.capstone_id, c.capstone_title, c.capstone_year
                FROM advisory_student r JOIN author a ON a.user_id = r.student_user_id
                JOIN capauth ca ON ca.author_id = a.author_id AND ca.role = 'Author'
                JOIN capstone c ON c.capstone_id = ca.capstone_id
                WHERE r.professor_user_id = %s AND c.is_archived IS NOT TRUE
                ORDER BY c.capstone_year DESC NULLS LAST, c.capstone_title, c.capstone_id
            """, (professor_id,))
            for work in cursor.fetchall():
                if work["user_id"] in by_id:
                    by_id[work["user_id"]]["works"].append(work)
            return students
    finally:
        conn.close()


def get_available_advisory_students(professor_id):
    conn = db_connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            _require_professor(cursor, professor_id)
            cursor.execute('''
                SELECT u.user_id, u.university_no,
                       CONCAT_WS(' ', u.user_first_name, u.user_middle_name, u.user_last_name) AS full_name
                FROM "user" u WHERE u.role_id = 1 AND u.account_status = 'active'
                  AND NOT EXISTS (SELECT 1 FROM advisory_student r
                                  WHERE r.professor_user_id = %s AND r.student_user_id = u.user_id)
                ORDER BY u.user_last_name, u.user_first_name, u.user_id
            ''', (professor_id,))
            return cursor.fetchall()
    finally:
        conn.close()


def _change_roster(professor_id, student_ids, *, group_id=None, remove=False):
    if not student_ids or len(student_ids) != len(set(student_ids)):
        return False, "Select at least one student, with no duplicate accounts."
    if not remove and len(student_ids) > MAX_ADVISORY_GROUP_STUDENTS:
        return False, f"Groups can have at most {MAX_ADVISORY_GROUP_STUDENTS} students."
    conn = db_connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            # Stable lock order handles duplicate submissions and role/status changes.
            cursor.execute('''
                SELECT user_id, role_id, account_status FROM "user"
                WHERE user_id = ANY(%s) ORDER BY user_id FOR NO KEY UPDATE
            ''', ([professor_id, *student_ids],))
            users = {row["user_id"]: row for row in cursor.fetchall()}
            professor = users.get(professor_id)
            if not professor or professor["role_id"] != 4 or professor["account_status"] != "active":
                raise ValueError("Only an active capstone professor can manage an advisory roster.")
            if professor_id in student_ids:
                raise ValueError("You cannot add yourself as an advisory student.")
            if remove:
                student_id = student_ids[0]
                cursor.execute("""
                    DELETE FROM advisory_student
                    WHERE professor_user_id = %s AND student_user_id = %s RETURNING group_id
                """, (professor_id, student_id))
                removed = cursor.fetchone()
                if not removed:
                    raise ValueError("This student is not on your advisory roster.")
                group_id = removed["group_id"]
            else:
                _add_students_in_cursor(cursor, professor_id, student_ids, group_id)
            for student_id in student_ids:
                if remove:
                    log_audit(cursor, professor_id, "remove_advisory_student", "advisory_student", student_id,
                              new_values=f"professor_user_id={professor_id}; student_user_id={student_id}; group_id={group_id}")
        conn.commit()
        return True, None
    except ValueError as exc:
        conn.rollback()
        return False, str(exc)
    except Exception as exc:
        conn.rollback()
        logger.error("Advisory roster database error: %s", exc)
        return False, "Could not update your advisory roster. Please try again."
    finally:
        conn.close()


def add_advisory_student(professor_id, student_id, group_id):
    return add_advisory_students(professor_id, [student_id], group_id)


def add_advisory_students(professor_id, student_ids, group_id):
    return _change_roster(professor_id, student_ids, group_id=group_id)


def remove_advisory_student(professor_id, student_id):
    return _change_roster(professor_id, [student_id], remove=True)
