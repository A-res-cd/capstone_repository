import re
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config

def db_connect():
    conn = psycopg2.connect(
        host=Config.PG_HOST,
        port=Config.PG_PORT,
        user=Config.PG_USER,
        password=Config.PG_PASSWORD,
        database=Config.PG_DB,
    )

    return conn



# student and faculty auto detection role pattern
STUDENT_PATTERN = re.compile(r'^2\d{9}$|^2\d{3}-\d{5}$|^[A-Z]{2,4}\d{4}-\d{5}$', re.IGNORECASE)
PROFESSOR_PATTERN = re.compile(r'^\d{4}$')
ADMIN_PATTERN = re.compile(r'^admin\d{3}$', re.IGNORECASE)
# this should detect the role thingy

# validation patterns
EMAIL_PATTERN    = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_]{3,30}$')


def detect_role(university_no):
    if STUDENT_PATTERN.match(university_no):
        return "Student"
    if PROFESSOR_PATTERN.match(university_no):
        return "Faculty"
    if ADMIN_PATTERN.match(university_no):
        return "Admin"
    return None

# _____________________________________helper functions gang_______________________________ ps i was getting lost in the code so therese allat of notes now


def get_device_ip(request):
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr


def get_role_id(mithrix, role_name):
    mithrix.execute("""SELECT role_id FROM role
                       WHERE LOWER(role_name) = LOWER(%s) LIMIT 1""", (role_name,))
    row = mithrix.fetchone()
    return row[0] if row else None


def log_audit(mithrix, user_id, action_type, affected_table, affected_record_id, old_values=None, new_values=None):
    mithrix.execute("""
        INSERT INTO audit
        (user_id, action_type, affected_table, affected_record_id, old_values, new_values, action_timestamp)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (user_id, action_type, affected_table, affected_record_id, old_values, new_values, datetime.now(timezone.utc)))


# ___________________________________this be the sign up i think maybe______________________________
def create_user(first_name, middle_name, last_name, university_no, email, username, password):

    #strip and basic validation
    first_name    = first_name.strip()    if first_name    else ""
    middle_name   = middle_name.strip()   if middle_name   else ""
    last_name     = last_name.strip()     if last_name     else ""
    university_no = university_no.strip() if university_no else None
    email         = email.strip()         if email         else ""
    username      = username.strip()      if username      else ""
    role_name = detect_role(university_no) if university_no else "Student"

    #validation
    if not all([first_name, last_name, email, username, password]):
        return False, "All required fields must be filled in."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    if not EMAIL_PATTERN.match(email):
        return False, "Invalid email format."
    if not USERNAME_PATTERN.match(username):
        return False, "Username must be 3-30 characters, letters, numbers, and underscores only."
    
    if university_no and role_name is None:
        print(f"University number '{university_no}' did not match any known patterns.")
        return False, ("University number format not recognized")

    conn = db_connect()
    mithrix = conn.cursor()
    now = datetime.now(timezone.utc)

    try:
        role_id = get_role_id(mithrix, role_name)
        if role_id is None:
            return False, f"Role '{role_name}' is not in the system"

        # insert to user table
        mithrix.execute("""INSERT INTO "user"
            (role_id, user_first_name, user_middle_name,
            user_last_name, university_no)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING user_id
            """, (role_id, first_name, middle_name, last_name, university_no))
        user_id = mithrix.fetchone()[0]

        # insert into username table
        mithrix.execute("""INSERT INTO kappa (username)
            VALUES (%s)
            RETURNING username_id
        """, (username,))
        username_id = mithrix.fetchone()[0]

        # insert you know what
        mithrix.execute("""INSERT INTO ror (password, updated_at, previous_password_id)
            VALUES (%s, %s, NULL)
            RETURNING password_id
        """, (generate_password_hash(password), now))
        password_id = mithrix.fetchone()[0]

        # insert the owner
        mithrix.execute("""INSERT INTO slug
            (username_id, password_id, user_id,
            assigned_at, updated_at, is_current)
            VALUES (%s, %s, %s, %s, %s, TRUE)
        """, (username_id, password_id, user_id, now, now))

        # insert contact
        mithrix.execute("""INSERT INTO contact
            (user_id, contact_type, contact_value,
            is_primary, created_at)
            VALUES (%s, 'email', %s, TRUE, %s)
        """, (user_id, email.lower(), now))

        # add log to sign up tble
        mithrix.execute("""
            INSERT INTO signup (user_id, registration_date)
            VALUES (%s, %s)
            RETURNING signup_id
        """, (user_id, now))
        signup_id = mithrix.fetchone()[0]

        log_audit(mithrix, user_id, "signup", "signup", signup_id)

        conn.commit()
        return True, None

    except psycopg2.errors.UniqueViolation as exc:
        conn.rollback()
        detail = str(exc)
        if "kappa" in detail or "username" in detail:
            msg = "That username is already taken."
        elif "contact" in detail or "contact_value" in detail:
            msg = "That email is already registered."
        elif "university_no" in detail:
            msg = "That University number is already in use."
        else:
            msg = "A duplicate-entry error occurred."
        return False, msg

    except Exception as exc:
        conn.rollback()
        return False, f"Database error: {exc}"

    finally:
        mithrix.close()
        conn.close()

# ____________________________sign in or authentication idk_______________________
LOCKOUT_THRESHOLD = 5 # number of allowed failed attempts before lockout
LOCKOUT_DURATION = 20 # lockout duration in minutes

def sign_in(username, password, device_ip=None):
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    now = datetime.now(timezone.utc)

    try:
        mithrix.execute("""
        SELECT u.user_id, u.locked_until, k.username, r.password AS password_hash, ro.role_id, ro.role_name
        FROM kappa k
        JOIN slug sl ON sl.username_id = k.username_id AND sl.is_current = TRUE
        JOIN ror   r  ON r.password_id  = sl.password_id
        JOIN "user" u ON u.user_id      = sl.user_id
        JOIN role  ro ON ro.role_id     = u.role_id
        WHERE k.username = %s
        LIMIT 1
        """, (username,))

        row = mithrix.fetchone()

        if not row:
            return None, "Invalid username or password."
        
#start of new sign in with lockout and audit logging (if the bruth force defence is not needed delete the code from here to the end of the next comment)        
        if row["locked_until"]:
            locked_until = row["locked_until"]
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=timezone.utc)
            if now < locked_until:
                remaining = int((locked_until - now).total_seconds() // 60) + 1
                return None, f"Account locked. Try again in {remaining} minute(s)."
            else:
                # lockout expired, clear it and continue
                mithrix.execute("""
                    UPDATE "user" SET locked_until = NULL WHERE user_id = %s
                """, (row["user_id"],))
                conn.commit()  # commit the clear before continuing

        if not check_password_hash(row["password_hash"], password):

            mithrix.execute("""
                INSERT INTO login (user_id, log_in_time, login_device_ip, failed_attempts)
                VALUES (%s, %s, %s, 1)
                RETURNING log_in_id
            """, (row["user_id"], now, device_ip))

            mithrix.execute("""
                SELECT COUNT(*) AS fails
                FROM login
                WHERE user_id = %s
                  AND failed_attempts > 0
                  AND log_in_time >= NOW() - (%s * INTERVAL '1 minute')
            """, (row["user_id"], LOCKOUT_DURATION))
            fails = mithrix.fetchone()["fails"]

            if fails >= LOCKOUT_THRESHOLD:
                from datetime import timedelta
                mithrix.execute("""
                    UPDATE "user"
                    SET locked_until = %s
                    WHERE user_id = %s
                """, (now + timedelta(minutes=LOCKOUT_DURATION), row["user_id"]))
                conn.commit()
                return None, f"Too many failed attempts. Account locked for {LOCKOUT_DURATION} minutes."

            conn.commit()
            remaining_attempts = LOCKOUT_THRESHOLD - fails
            return None, f"Invalid username or password. {remaining_attempts} attempt(s) remaining before lockout."
        
        user_id = row["user_id"]

        mithrix.execute("""
            UPDATE login
            SET failed_attempts = 0
            WHERE user_id = %s AND failed_attempts > 0
        """, (row["user_id"],))

        mithrix.execute("""
            INSERT INTO login (user_id, log_in_time, login_device_ip, failed_attempts)
            VALUES (%s, %s, %s, 0)
            RETURNING log_in_id
        """, (user_id, now, device_ip))
        log_in_id = mithrix.fetchone()["log_in_id"]

        log_audit(mithrix, user_id, "login", "login", log_in_id)

        conn.commit()

        return {
            "user_id":   user_id,
            "username":  row["username"],
            "role_id":   row["role_id"],
            "role_name": row["role_name"],
        }, None

    except Exception as exc:
        conn.rollback()
        return None, f"Database error: {exc}"

    finally:
        mithrix.close()
        conn.close()
#end of new sign in with lockout and audit logging




# _______________forgot password stuffs_____________
OTP_EXPIRY_MINUTES = 4
OTP_MAX_ATTEMPTS = 2


def lookup_user_for_reset(username, email):
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        mithrix.execute("""
            SELECT u.user_id, c.contact_id
            FROM kappa k
            JOIN slug sl ON sl.username_id = k.username_id AND sl.is_current = TRUE
            JOIN "user" u ON u.user_id = sl.user_id
            JOIN contact c ON c.user_id = u.user_id AND c.contact_type = 'email' AND c.is_primary = TRUE
            WHERE k.username = %s AND LOWER(c.contact_value) = LOWER(%s) LIMIT 1            
        """, (username, email))

        row = mithrix.fetchone()

        if not row:
            return None, None, "No account with those credentials"

        return row["contact_id"], row["user_id"], None

    except Exception as exc:
        return None, None, f"Database error: {exc}"

    finally:
        mithrix.close()
        conn.close()


def create_otp(contact_id):
    import random

    otp = f"{random.randint(0, 999999):06d}"

    conn = db_connect()
    mithrix = conn.cursor()
    now = datetime.now(timezone.utc)
    expiry = now.replace(second=now.second)

    from datetime import timedelta
    expiry = now + timedelta(minutes=OTP_EXPIRY_MINUTES)

    try:
        mithrix .execute("""
            UPDATE password_reset
            SET is_used = TRUE
            WHERE contact_id = %s AND is_used = FALSE
        """, (contact_id,))

        mithrix.execute("""
            INSERT INTO password_reset(contact_id, reset_token, expiry_date, is_primary, is_used, created_at)
            VALUES(%s, %s, %s, TRUE, FALSE, %s)
            RETURNING reset_id
        """, (contact_id, generate_password_hash(otp), expiry, now))
        reset_id = mithrix.fetchone()[0]

        conn.commit()
        return otp, reset_id

    except Exception as exc:
        raise RuntimeError(f"Could not create OTP: {exc}")

    finally:
        mithrix.close()
        conn.close()


def verify_otp(reset_id, otp_entered):

    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    now = datetime.now(timezone.utc)

    try:
        mithrix.execute("""
            SELECT reset_id, reset_token, expiry_date, is_used, COALESCE(attempt_count, 0) AS attempt_count
            FROM password_reset
            WHERE reset_id = %s
        """, (reset_id,))
        row = mithrix.fetchone()

        if not row:
            return False, "invalid reset token"
        if row["is_used"]:
            return False, "This reset token has alredy been used"
        expiry = row["expiry_date"]
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if now > expiry:
            return False, "OTP has expired. Please request a new one"
        if row["attempt_count"] >= OTP_MAX_ATTEMPTS:
            return False, "Too many incorect attempts. Please request a new reset token"
        if not check_password_hash(row["reset_token"], otp_entered):
            mithrix.execute("""
                UPDATE password_reset
                SET attempt_count = COALESCE(attempt_count, 0) + 1
                WHERE reset_id = %s
            """, (reset_id,))
            conn.commit()
            remaining = OTP_MAX_ATTEMPTS - (row["attempt_count"] + 1)
            if remaining <= 0:
                return False, "Too many incorrect attempts. Please request a new OTP."
            return False, f"Incorrect OTP. {remaining} attempt(s) remaining."

        log_audit(mithrix, None, "otp_verified", "password_reset",
                  reset_id, old_values="unused", new_values="verified")

        conn.commit()
        return True, None

    except Exception as exc:
        conn.rollback()
        return False, f"Database error: {exc}"

    finally:
        mithrix.close()
        conn.close()


def change_password(reset_id, user_id, new_password):

    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    now = datetime.now(timezone.utc)

    try:
        mithrix.execute("""
            SELECT password_id FROM slug
            WHERE user_id   = %s
            AND is_current = TRUE
            LIMIT 1
        """, (user_id,))
        row = mithrix.fetchone()
        old_password_id = row["password_id"] if row else None

        mithrix.execute("""
            INSERT INTO ror (password, updated_at, previous_password_id)
            VALUES (%s, %s, %s)
            RETURNING password_id
        """, (generate_password_hash(new_password), now, old_password_id))
        new_password_id = mithrix.fetchone()["password_id"]

        mithrix.execute(""" 
            UPDATE slug SET is_current = FALSE
            WHERE user_id = %s AND is_current = TRUE
        """, (user_id,))

        mithrix.execute("""
            INSERT INTO slug (username_id, password_id, user_id,
                              assigned_at, updated_at, is_current)
            SELECT username_id, %s, %s, %s, %s, TRUE
            FROM slug
            WHERE user_id = %s
            ORDER BY assigned_at DESC
            LIMIT 1
        """, (new_password_id, user_id, now, now, user_id))

        mithrix.execute("""
            UPDATE password_reset SET is_used = TRUE
            WHERE reset_id = %s
        """, (reset_id,))

        log_audit(mithrix, user_id, 'password_reset', 'ror', new_password_id,
                  old_values=str(old_password_id), new_values=str(new_password_id))

        conn.commit()
        return True, None

    except Exception as exc:
        conn.rollback()
        return False, f"Database error: {exc}"

    finally:
        mithrix.close()
        conn.close()


def sign_out(user_id, device_ip=None):
    conn = db_connect()
    mithrix = conn.cursor()
    now = datetime.now(timezone.utc)

    try:
        # write to logOut table
        mithrix.execute("""
            INSERT INTO logOut (user_id, log_out_time, logout_device_ip)
            VALUES (%s, %s, %s)
            RETURNING log_out_id
        """, (user_id, now, device_ip))
        log_out_id = mithrix.fetchone()[0]

        log_audit(
            mithrix, user_id,
            "logout", "logOut", log_out_id,
            old_values=None,
            new_values=str(log_out_id)
        )

        conn.commit()
        return True, None

    except Exception as exc:
        conn.rollback()
        return False, f"Database error: {exc}"

    finally:
        mithrix.close()
        conn.close()
# ______________________________Admin CRUD Operations for Manage Capstone Repository___________________________


def create_capstone_project(keyword_id, specialization_id, program_id,
                            capstone_title, capstone_year, capstone_file,
                            citation_count, semester, term=None):
    conn = db_connect()
    mithrix = conn.cursor()
    try:
        mithrix.execute("""
            INSERT INTO capstone(keyword_id, specialization_id, program_id,
                        capstone_title, capstone_year, capstone_file,
                        citation_count, semester, term)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING capstone_id
        """, (keyword_id, specialization_id, program_id, capstone_title,
              capstone_year, capstone_file, citation_count, semester, term))
        capstone_id = mithrix.fetchone()[0]
        conn.commit()
        return True, capstone_id
    except Exception as exc:
        conn.rollback()
        return False, f"Database error: {exc}"
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
        return False, f"Database error: {exc}"
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
        return False, f"Database error: {exc}"
    finally:
        mithrix.close()
        conn.close()


def get_capstone_details(capstone_id):
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        mithrix.execute("""
            SELECT c.capstone_id, c.capstone_title, c.capstone_year, c.capstone_file,
                   c.citation_count, c.semester, c.term,
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
        return None
    finally:
        mithrix.close()
        conn.close()


def update_capstone_record(capstone_id, keyword_id, specialization_id, program_id,
                           capstone_title, capstone_year, capstone_file,
                           citation_count, semester, term=None):
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
                citation_count = %s,
                semester = %s,
                term = %s
            WHERE capstone_id = %s
        """, (keyword_id, specialization_id, program_id, capstone_title,
              capstone_year, capstone_file, citation_count, semester, term, capstone_id))
        conn.commit()
        return True, None
    except Exception as exc:
        conn.rollback()
        return False, f"Database error: {exc}"
    finally:
        mithrix.close()
        conn.close()


def get_all_capstones():
    """
    Retrieve all capstone projects with their details
    """
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        mithrix.execute("""
            SELECT c.capstone_id, c.capstone_title, c.capstone_year, c.capstone_file,
                   c.citation_count, c.semester, c.term,
                   k.keyword_id, k.capstone_keywords,
                   s.specialization_id, s.specialization_name,
                   p.program_id, p.program_name
            FROM capstone c
            JOIN keyword k ON c.keyword_id = k.keyword_id
            JOIN specialization s ON c.specialization_id = s.specialization_id
            JOIN program p ON c.program_id = p.program_id
            ORDER BY c.capstone_year DESC, c.capstone_id DESC
        """)
        return mithrix.fetchall()
    except Exception as exc:
        print(f'Error: {exc}')
        return []
    finally:
        mithrix.close()
        conn.close()


def delete_capstone(capstone_id):
    """
    Delete a capstone project by ID with cascading deletes for related records
    """
    conn = db_connect()
    mithrix = conn.cursor()
    try:
        # get keyword_id for potential cleanup
        mithrix.execute("""
            SELECT keyword_id FROM capstone WHERE capstone_id = %s
        """, (capstone_id,))
        row = mithrix.fetchone()
        if not row:
            return False, "Capstone not found."
        keyword_id = row[0]

        # delete related capAuth entries first (authors/advisers)
        mithrix.execute("""
            DELETE FROM capAuth WHERE capstone_id = %s
        """, (capstone_id,))

        mithrix.execute("""
            DELETE FROM capstone WHERE capstone_id = %s
        """, (capstone_id,))
        
        #delete the keyword if no other capstone is using it
        mithrix.execute("""
            DELETE FROM keyword
            WHERE keyword_id = %s
              AND NOT EXISTS (
                  SELECT 1 FROM capstone WHERE keyword_id = %s
              )
        """, (keyword_id, keyword_id))

        conn.commit()
        return True, "Capstone deleted successfully"
    except Exception as exc:
        conn.rollback()
        return False, f"Database error: {exc}"
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

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

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

    except Exception:
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
    except Exception:
        return []
    finally:
        mithrix.close()
        conn.close()




# ______________________________Manage Users___________________________

def get_users():
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        mithrix.execute("""
            SELECT u.user_id,
                   CONCAT_WS(' ', u.user_first_name, u.user_middle_name, u.user_last_name) AS full_name,
                   u.university_no,
                   r.role_name AS role,
                   c.contact_value AS email
            FROM "user" u
            JOIN role r ON u.role_id = r.role_id
            LEFT JOIN contact c ON c.user_id = u.user_id AND c.contact_type = 'email' AND c.is_primary = TRUE
            ORDER BY u.user_id
        """)
        return mithrix.fetchall()
    except Exception:
        return []
    finally:
        mithrix.close()
        conn.close()

def get_all_roles():
    """Return all roles as (role_id, role_name) tuples for template dropdowns."""
    conn = db_connect()
    mithrix = conn.cursor()
    try:
        mithrix.execute('SELECT role_id, role_name FROM "role" ORDER BY role_id')
        return mithrix.fetchall()
    except Exception:
        return []
    finally:
        mithrix.close()
        conn.close()


def update_user_role(user_id, new_role_id, acting_admin_id):
    """Change a user's role and write an audit entry."""
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        # capture old role for audit
        mithrix.execute(
            'SELECT role_id FROM "user" WHERE user_id = %s', (user_id,)
        )
        row = mithrix.fetchone()
        old_role_id = row["role_id"] if row else None

        mithrix.execute(
            'UPDATE "user" SET role_id = %s WHERE user_id = %s',
            (new_role_id, user_id),
        )

        log_audit(
            mithrix, acting_admin_id,
            "role_change", "user", user_id,
            old_values=str(old_role_id),
            new_values=str(new_role_id),
        )

        conn.commit()
        return True, None
    except Exception as exc:
        conn.rollback()
        return False, f"Database error: {exc}"
    finally:
        mithrix.close()
        conn.close()


def delete_user_account(user_id, acting_admin_id):
    """
    Hard-delete a user and all dependent rows.
    Order matters — FK constraints cascade from least to most dependent.
    """
    conn = db_connect()
    mithrix = conn.cursor()
    try:
        # audit first, while user still exists
        log_audit(mithrix, acting_admin_id, "delete_user", "user", user_id)

        # remove auth chain
        mithrix.execute("""
            DELETE FROM slug WHERE user_id = %s
        """, (user_id,))

        mithrix.execute("""
            DELETE FROM login   WHERE user_id = %s
        """, (user_id,))

        mithrix.execute("""
            DELETE FROM logOut  WHERE user_id = %s
        """, (user_id,))

        mithrix.execute("""
            DELETE FROM signup  WHERE user_id = %s
        """, (user_id,))

        mithrix.execute("""
            DELETE FROM contact WHERE user_id = %s
        """, (user_id,))

        # finally the user row itself
        mithrix.execute("""
            DELETE FROM "user"  WHERE user_id = %s
        """, (user_id,))

        conn.commit()
        return True, None
    except Exception as exc:
        conn.rollback()
        return False, f"Database error: {exc}"
    finally:
        mithrix.close()
        conn.close()


def request_fullview(user_id, capstone_id, request_reason):
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    now = datetime.now(timezone.utc)

    try:
        mithrix.execute("""
            INSERT INTO request(user_id, capstone_id, request_status, request_reason, request_date)
            VALUES(%s, %s, 'pending', %s,  %s)
            RETURNING request_id
        """, (user_id, capstone_id, request_reason, now))


        request_id = mithrix.fetchone()["request_id"]
        log_audit(mithrix, user_id, "manuscript_request", "manuscript_request", request_id)

        conn.commit()
        return True, None
    
    except Exception as exc:
        conn.rollback()
        return False, f"Database error: {exc}"
    
    finally:
        mithrix.close()
        conn.close()

def get_all_requests():
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        mithrix.execute("""
            SELECT r.*, c.capstone_title,
            CONCAT_WS('', u.user_first_name, u.user_last_name) AS requester_name
            FROM request r
            JOIN capstone c ON c.capstone_id = r.capstone_id
            JOIN "user" u ON u.user_id = r.user_id
            ORDER BY r.request_date DESC
        """)

        return mithrix.fetchall()
    
    except Exception as exc:
        return []
    
    finally:
        mithrix.close()
        conn.close()

def review_request(request_id, request_status, status_reason, reviewed_by):
    conn = db_connect()
    mithrix = conn.cursor()
    now = datetime.now(timezone.utc)

    try:
        mithrix.execute("""
            UPDATE request SET 
            request_status = %s,
            status_reason = %s,
            reviewed_by = %s,
            decision_date = %s
            WHERE request_id = %s         
        """, (request_status, status_reason, reviewed_by, now, request_id))

        conn.commit()
        return True, None
    except Exception as exc:
        conn.rollback()
        return False, f"Database error: {exc}"
    
    finally:
        mithrix.close()
        conn.close()

#I DONT WANNA DO THIS ANYMOREEEEEEEEEE

def get_user_requests(user_id):
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        mithrix.execute("""
            SELECT r.*, c.capstone_title, c.capstone_id, s.specialization_name, c.capstone_year
            FROM request r
            JOIN capstone c ON c.capstone_id  = r.capstone_id
            JOIN specialization s ON s.specialization_id = c.specialization_id
            WHERE r.user_id = %s
            ORDER BY r.request_date DESC
        """, (user_id, ))

        return mithrix.fetchall()
    except Exception as exc:
        return []
    
    finally:
        mithrix.close()
        conn.close()


# ______________________________Admin Analytics___________________________

def get_capstones_by_program():
    """Capstone count grouped by program — for the Analytics bar chart."""
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        mithrix.execute("""
            SELECT p.program_name, COUNT(*) AS total
            FROM capstone c
            JOIN program p ON p.program_id = c.program_id
            GROUP BY p.program_name
            ORDER BY total DESC
        """)
        return mithrix.fetchall()
    except Exception:
        return []
    finally:
        mithrix.close()
        conn.close()


def get_requests_by_status():
    """Request count grouped by status — for the Analytics donut chart."""
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        mithrix.execute("""
            SELECT request_status, COUNT(*) AS total
            FROM request
            GROUP BY request_status
            ORDER BY total DESC
        """)
        return mithrix.fetchall()
    except Exception:
        return []
    finally:
        mithrix.close()
        conn.close()


def get_top_cited_capstones(limit=5):
    """Highest citation_count capstones — for the Analytics leaderboard."""
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        mithrix.execute("""
            SELECT c.capstone_id, c.capstone_title, c.citation_count, p.program_name
            FROM capstone c
            JOIN program p ON p.program_id = c.program_id
            WHERE c.citation_count > 0
            ORDER BY c.citation_count DESC, c.capstone_title ASC
            LIMIT %s
        """, (limit,))
        return mithrix.fetchall()
    except Exception:
        return []
    finally:
        mithrix.close()
        conn.close()


#FAHHHHH ANG DAMI FUNCTIONSSSSSSSS IM SICK AND TIRED OF THISSSSSSS
def cancel_manuscript_request(request_id, user_id):
    conn = db_connect()
    mithrix = conn.cursor()

    try:
        mithrix.execute("""
            UPDATE request
            SET request_status = 'cancelled'
            WHERE request_id = %s AND user_id = %s
            AND request_status = 'pending'
        """, (request_id, user_id))
        
        conn.commit()
        return True, None
    
    except Exception as exc:
        conn.rollback()
        return False, f"Database error: {exc}"
    
    finally:
        mithrix.close()
        conn.close()

def add_citations(capstone_id):
    conn = db_connect()
    mithrix = conn.cursor()

    try:
        mithrix.execute("""
            UPDATE capstone
            SET citation_count = citation_count + 1
            WHERE capstone_id = %s
        """, (capstone_id, ))

        conn.commit()
        return True, None
    except Exception as exc:
        conn.rollback()
        return False, f"Database Error: {exc}"
    
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
    
    except Exception:
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
        return []
    
    finally:
        conn.close()
        mithrix.close()

def set_capstone_people(capstone_id, authors, adviser):
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

        conn.commit()
        return True, None
    except Exception as exc:
        conn.rollback()
        return False, f"Database error: {exc}"
    finally:
        mithrix.close()
        conn.close()
