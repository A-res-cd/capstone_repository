"""Database operations for adviser requirements and student progress."""

import psycopg2.extras

from app.db.connection import db_connect


def _require_professor(cursor, professor_id):
    cursor.execute('''
        SELECT user_id FROM "user"
        WHERE user_id = %s AND role_id = 4 AND account_status = 'active'
    ''', (professor_id,))
    if not cursor.fetchone():
        raise PermissionError("Only an active capstone professor can manage progress.")


def get_student_progress(student_id):
    conn = db_connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("""
                SELECT req.requirement_id, req.professor_user_id, req.group_id,
                       req.title, req.instructions, req.due_date, req.created_at,
                       grp.group_name,
                       CONCAT_WS(' ', professor.user_first_name, professor.user_last_name) AS professor_name,
                       CASE WHEN professor.role_id = 4 AND professor.account_status = 'active'
                            THEN 'active' ELSE 'inactive' END AS professor_status,
                       latest.submission_id, latest.submission_kind, latest.external_url,
                       latest.original_filename, latest.student_note, latest.review_status,
                       latest.advisor_feedback, latest.submitted_at, latest.reviewed_at
                FROM advisory_requirement req
                JOIN advisory_group grp ON grp.group_id = req.group_id
                    AND grp.professor_user_id = req.professor_user_id
                JOIN advisory_student roster ON roster.professor_user_id = req.professor_user_id
                    AND roster.group_id = req.group_id AND roster.student_user_id = %s
                JOIN "user" professor ON professor.user_id = req.professor_user_id
                LEFT JOIN LATERAL (
                    SELECT sub.submission_id, sub.submission_kind, sub.external_url,
                           sub.original_filename, sub.student_note, sub.review_status,
                           sub.advisor_feedback, sub.submitted_at, sub.reviewed_at
                    FROM advisory_submission sub
                    WHERE sub.professor_user_id = req.professor_user_id
                      AND sub.requirement_id = req.requirement_id
                      AND sub.student_user_id = %s
                    ORDER BY sub.submitted_at DESC, sub.submission_id DESC
                    LIMIT 1
                ) latest ON TRUE
                WHERE req.is_active
                ORDER BY professor.user_last_name, grp.group_name, req.created_at, req.requirement_id
            """, (student_id, student_id))
            requirements = [dict(row) for row in cursor.fetchall()]
            requirement_ids = [row["requirement_id"] for row in requirements]
            if requirement_ids:
                cursor.execute("""
                    SELECT submission_id, requirement_id, submission_kind, external_url,
                           original_filename, student_note, review_status, advisor_feedback,
                           submitted_at, reviewed_at
                    FROM advisory_submission
                    WHERE student_user_id = %s AND requirement_id = ANY(%s)
                    ORDER BY submitted_at DESC, submission_id DESC
                """, (student_id, requirement_ids))
                history = {}
                for row in cursor.fetchall():
                    history.setdefault(row["requirement_id"], []).append(dict(row))
                for requirement in requirements:
                    requirement["history"] = history.get(requirement["requirement_id"], [])
            else:
                for requirement in requirements:
                    requirement["history"] = []
            return requirements
    finally:
        conn.close()


def get_advisor_group_progress(professor_id, group_id):
    conn = db_connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            _require_professor(cursor, professor_id)
            cursor.execute("""
                SELECT group_id, group_name FROM advisory_group
                WHERE professor_user_id = %s AND group_id = %s
            """, (professor_id, group_id))
            group = cursor.fetchone()
            if not group:
                return None

            cursor.execute("""
                SELECT roster.student_user_id AS user_id,
                       CONCAT_WS(' ', student.user_first_name, student.user_middle_name,
                                 student.user_last_name) AS full_name,
                       student.university_no
                FROM advisory_student roster
                JOIN "user" student ON student.user_id = roster.student_user_id
                WHERE roster.professor_user_id = %s AND roster.group_id = %s
                ORDER BY student.user_last_name, student.user_first_name, student.user_id
            """, (professor_id, group_id))
            students = [dict(row) for row in cursor.fetchall()]

            cursor.execute("""
                SELECT requirement_id, title, instructions, due_date, created_at
                FROM advisory_requirement
                WHERE professor_user_id = %s AND group_id = %s AND is_active
                ORDER BY created_at, requirement_id
            """, (professor_id, group_id))
            requirements = [dict(row) for row in cursor.fetchall()]

            if requirements and students:
                requirement_ids = [row["requirement_id"] for row in requirements]
                student_ids = [row["user_id"] for row in students]
                cursor.execute("""
                    SELECT DISTINCT ON (sub.requirement_id, sub.student_user_id)
                           sub.requirement_id, sub.student_user_id, sub.submission_id,
                           sub.submission_kind, sub.external_url, sub.original_filename,
                           sub.student_note, sub.review_status, sub.advisor_feedback,
                           sub.submitted_at, sub.reviewed_at
                    FROM advisory_submission sub
                    WHERE sub.professor_user_id = %s
                      AND sub.requirement_id = ANY(%s)
                      AND sub.student_user_id = ANY(%s)
                    ORDER BY sub.requirement_id, sub.student_user_id,
                             sub.submitted_at DESC, sub.submission_id DESC
                """, (professor_id, requirement_ids, student_ids))
                latest = {
                    (row["requirement_id"], row["student_user_id"]): dict(row)
                    for row in cursor.fetchall()
                }
            else:
                latest = {}

            for requirement in requirements:
                requirement["progress"] = []
                for student in students:
                    item = dict(student)
                    item["submission"] = latest.get(
                        (requirement["requirement_id"], student["user_id"])
                    )
                    requirement["progress"].append(item)

            all_submissions = [item["submission"] for req in requirements
                               for item in req["progress"] if item["submission"]]
            return {
                "group": dict(group),
                "students": students,
                "requirements": requirements,
                "submitted_count": sum(bool(item) for item in all_submissions),
                "approved_count": sum(item["review_status"] == "approved" for item in all_submissions),
            }
    finally:
        conn.close()


def create_advisory_requirement(professor_id, group_id, title, instructions, due_date):
    conn = db_connect()
    try:
        with conn.cursor() as cursor:
            _require_professor(cursor, professor_id)
            cursor.execute("""
                INSERT INTO advisory_requirement
                    (professor_user_id, group_id, title, instructions, due_date)
                SELECT %s, group_id, %s, %s, %s
                FROM advisory_group
                WHERE professor_user_id = %s AND group_id = %s
                RETURNING requirement_id
            """, (professor_id, title, instructions, due_date, professor_id, group_id))
            row = cursor.fetchone()
            if not row:
                conn.rollback()
                return False
            conn.commit()
            return row[0]
    finally:
        conn.close()


def archive_advisory_requirement(professor_id, requirement_id):
    conn = db_connect()
    try:
        with conn.cursor() as cursor:
            _require_professor(cursor, professor_id)
            cursor.execute("""
                UPDATE advisory_requirement SET is_active = FALSE
                WHERE professor_user_id = %s AND requirement_id = %s AND is_active
                RETURNING requirement_id
            """, (professor_id, requirement_id))
            changed = cursor.fetchone() is not None
            conn.commit()
            return changed
    finally:
        conn.close()


def submit_advisory_requirement(student_id, requirement_id, values):
    conn = db_connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT req.professor_user_id, req.group_id
                FROM advisory_requirement req
                JOIN advisory_student roster ON roster.professor_user_id = req.professor_user_id
                    AND roster.group_id = req.group_id AND roster.student_user_id = %s
                JOIN "user" professor ON professor.user_id = req.professor_user_id
                    AND professor.role_id = 4 AND professor.account_status = 'active'
                WHERE req.requirement_id = %s AND req.is_active
                FOR UPDATE OF req, roster
            """, (student_id, requirement_id))
            assignment = cursor.fetchone()
            if not assignment:
                raise PermissionError("This requirement is not on your active advisory progress list.")
            professor_id = assignment[0]
            cursor.execute("""
                SELECT review_status FROM advisory_submission
                WHERE professor_user_id = %s AND requirement_id = %s AND student_user_id = %s
                ORDER BY submitted_at DESC, submission_id DESC LIMIT 1
            """, (professor_id, requirement_id, student_id))
            latest = cursor.fetchone()
            if latest and latest[0] == "approved":
                raise ValueError("This requirement is already approved.")

            cursor.execute("""
                INSERT INTO advisory_submission
                    (professor_user_id, requirement_id, student_user_id, submission_kind,
                     external_url, storage_key, original_filename, mime_type, file_size, student_note)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING submission_id
            """, (professor_id, requirement_id, student_id,
                  values["submission_kind"], values.get("external_url"),
                  values.get("storage_key"), values.get("original_filename"),
                  values.get("mime_type"), values.get("file_size"), values.get("student_note", "")))
            submission_id = cursor.fetchone()[0]
            conn.commit()
            return submission_id
    finally:
        conn.close()


def review_advisory_submission(professor_id, submission_id, status, feedback):
    conn = db_connect()
    try:
        with conn.cursor() as cursor:
            _require_professor(cursor, professor_id)
            cursor.execute("""
                SELECT sub.requirement_id, sub.student_user_id
                FROM advisory_submission sub
                JOIN advisory_requirement req ON req.requirement_id = sub.requirement_id
                    AND req.professor_user_id = sub.professor_user_id
                JOIN advisory_student roster ON roster.professor_user_id = sub.professor_user_id
                    AND roster.group_id = req.group_id AND roster.student_user_id = sub.student_user_id
                WHERE sub.professor_user_id = %s AND sub.submission_id = %s AND req.is_active
                FOR UPDATE OF sub
            """, (professor_id, submission_id))
            row = cursor.fetchone()
            if not row:
                raise PermissionError("This submission is not available on your advisory roster.")
            requirement_id, student_id = row
            cursor.execute("""
                SELECT submission_id FROM advisory_submission
                WHERE professor_user_id = %s AND requirement_id = %s AND student_user_id = %s
                ORDER BY submitted_at DESC, submission_id DESC LIMIT 1
            """, (professor_id, requirement_id, student_id))
            latest = cursor.fetchone()
            if not latest or latest[0] != submission_id:
                raise ValueError("A newer submission exists. Review the latest version.")
            cursor.execute("""
                UPDATE advisory_submission
                SET review_status = %s, advisor_feedback = %s,
                    reviewed_by_user_id = %s, reviewed_at = CURRENT_TIMESTAMP
                WHERE submission_id = %s
            """, (status, feedback or None, professor_id, submission_id))
            conn.commit()
            return True
    finally:
        conn.close()


def get_professor_submission_file(professor_id, submission_id):
    conn = db_connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            _require_professor(cursor, professor_id)
            cursor.execute("""
                SELECT sub.storage_key, sub.original_filename, sub.mime_type
                FROM advisory_submission sub
                JOIN advisory_requirement req ON req.requirement_id = sub.requirement_id
                    AND req.professor_user_id = sub.professor_user_id
                JOIN advisory_student roster ON roster.professor_user_id = sub.professor_user_id
                    AND roster.group_id = req.group_id AND roster.student_user_id = sub.student_user_id
                WHERE sub.professor_user_id = %s AND sub.submission_id = %s
                  AND sub.submission_kind = 'file'
            """, (professor_id, submission_id))
            row = cursor.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def get_student_submission_file(student_id, submission_id):
    conn = db_connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("""
                SELECT storage_key, original_filename, mime_type
                FROM advisory_submission
                WHERE student_user_id = %s AND submission_id = %s AND submission_kind = 'file'
            """, (student_id, submission_id))
            row = cursor.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()
