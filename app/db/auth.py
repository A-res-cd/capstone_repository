"""
Authentication & account lifecycle: sign up, sign in/out, role
detection & verification, password reset/OTP, and pending-verification
review. Everything that touches the user, kappa, ror, slug, login,
logout, signup, or password_reset tables lives here.
"""
import re
import logging
import psycopg2.extras
from datetime import datetime, timedelta, timezone
from werkzeug.security import generate_password_hash, check_password_hash

from app.db.connection import db_connect
from app.db.audit import log_audit

logger = logging.getLogger(__name__)

# student and faculty auto detection role pattern
STUDENT_PATTERN = re.compile(r'^(?:[SUM]{3})?\d{4}-\d+$', re.IGNORECASE)
PROFESSOR_PATTERN = re.compile(r'^\d{4}$')
ADMIN_PATTERN = re.compile(r'^admin\d{3}$', re.IGNORECASE)

# validation patterns
EMAIL_PATTERN = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_]{3,30}$')

LOCKOUT_THRESHOLD = 5  # number of allowed failed attempts before lockout
LOCKOUT_DURATION = 20  # lockout duration in minutes

OTP_EXPIRY_MINUTES = 4
OTP_MAX_ATTEMPTS = 2


def detect_role(university_no):
    if STUDENT_PATTERN.match(university_no):
        return "Student"
    if PROFESSOR_PATTERN.match(university_no):
        return "Faculty"
    if ADMIN_PATTERN.match(university_no):
        return "Admin"
    return None

#new role assignment also returs something so we can assign it to the righgt (verificationist)

def get_verifier_track(role_name):
    if role_name == "Student":
        return "student"
    if role_name in ("Faculty", "Admin"):
        return "faculty"
    
    return None

#______________________________________The new request when sign up function_______________________________

def screen_account(mithrix, user_id, role_name):
    mithrix.execute("""
        SELECT account_status FROM "user"
        WHERE user_id = %s
    """, (user_id,))
    row = mithrix.fetchone()

    if not row:
        return None, "User not found"
    
    if row["account_status"] == "rejected":
        mithrix.execute("""
            UPDATE "user" SET account_status = 'pending'
            WHERE user_id = %s
        """, (user_id,))
        log_audit(mithrix, user_id, "reapplication", "user", user_id,
                  old_values="rejected", new_values="pending")
        
    track = get_verifier_track(role_name)
    if track is None:
        return None, "Could not determine a verification track for this role."
    
    return track, None

def create_verification_request(mithrix, user_id, track, fallback_email=None):
    now = datetime.now(timezone.utc)

    mithrix.execute("""
        INSERT INTO request(user_id, request_type, request_status, request_date)
        VALUES (%s, %s, 'pending', %s)
        RETURNING request_id
    """, (user_id, f"verification_{track}", now))
    request_id = mithrix.fetchone()["request_id"]

    log_audit(mithrix, user_id, "verification_request", "request", request_id)

    mithrix.execute("""
        SELECT contact_value FROM "contact"
        WHERE user_id = %s AND contact_type = 'email' AND is_primary = TRUE
    """, (user_id,))
    contact = mithrix.fetchone()

    return(contact["contact_value"] if contact else fallback_email), None

def reapply_for_verification(user_id):
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try: 
        mithrix.execute("""
            SELECT role_id FROM "user" 
            WHERE user_id = %s
        """, (user_id,))
        row = mithrix.fetchone()
        if not row:
            return False, "user not found"
        
        role_name = None
        mithrix.execute("""SELECT role_name FROM role 
        WHERE role_id = %s""", (row["role_id"],))

        role_row = mithrix.fetchone()
        if role_row:
            role_name = role_row["role_name"]

        track, error = screen_account(mithrix, user_id, role_name)
        if error:
            conn.rollback()
            return False, error
        
        confirm_email, error = create_verification_request(mithrix, user_id, track)
        if error:
            conn.rollback()
            return False, error
 
        conn.commit()
        return True, {"track": track, "email": confirm_email}
 
    except Exception as exc:
        conn.rollback()
        logger.error("Database error: %s", exc)
        return False, "Something went wrong creating your account. Please try again."
    finally:
        mithrix.close()
        conn.close()
# _____________________________________helper functions gang_______________________________ ps i was getting lost in the code so therese allat of notes now

def get_device_ip(request):
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr

def get_role_id(mithrix, role_name):
    mithrix.execute("""SELECT role_id FROM role
                       WHERE LOWER(role_name) = LOWER(%s) LIMIT 1""", (role_name,))
    row = mithrix.fetchone()
    return row["role_id"] if row else None

def create_user(first_name, middle_name, last_name, university_no, email, username, password):

    #strip and basic validation
    first_name    = first_name.strip()    if first_name    else ""
    middle_name   = middle_name.strip()   if middle_name   else ""
    last_name     = last_name.strip()     if last_name     else ""
    university_no = (university_no or "").strip()
    email         = email.strip()         if email         else ""
    username      = username.strip()      if username      else ""
    role_name = detect_role(university_no) if university_no else "Student"

    # validation
    if not all([first_name, last_name, email, username, password]):
        return False, "All required fields must be filled in."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    if not EMAIL_PATTERN.match(email):
        return False, "Invalid email format."
    if not USERNAME_PATTERN.match(username):
        return False, "Username must be 3-30 characters, letters, numbers, and underscores only."

    if university_no and role_name is None:
        logger.warning(
            "University number '%s' did not match any known patterns.", university_no)
        return False, ("University number format not recognized")

    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    now = datetime.now(timezone.utc)

    try:
        role_id = get_role_id(mithrix, role_name)
        if role_id is None:
            return False, f"Role '{role_name}' is not in the system"

        # insert to user table
        insert_university_no = university_no or None
        mithrix.execute("""INSERT INTO "user"
            (role_id, user_first_name, user_middle_name,
            user_last_name, university_no, account_status)
            VALUES (%s, %s, %s, %s, %s, 'pending')
            RETURNING user_id
            """, (role_id, first_name, middle_name, last_name, insert_university_no))
        user_id = mithrix.fetchone()["user_id"]

        # insert into username table
        mithrix.execute("""INSERT INTO kappa (username)
            VALUES (%s)
            RETURNING username_id
        """, (username,))
        username_id = mithrix.fetchone()["username_id"]

        # insert you know what
        mithrix.execute("""INSERT INTO ror (password, updated_at, previous_password_id)
            VALUES (%s, %s, NULL)
            RETURNING password_id
        """, (generate_password_hash(password), now))
        password_id = mithrix.fetchone()["password_id"]

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
        signup_id = mithrix.fetchone()["signup_id"]

        log_audit(mithrix, user_id, "signup", "signup", signup_id)


        # ------ 1.2.1 creena dn clasitfy------------
        track, error = screen_account(mithrix, user_id, role_name)
        if error:
            conn.rollback()
            return False, error

    
        # ------- 1.2.2 file verifiation request--------------
        confirm_email, error = create_verification_request(mithrix, user_id, track, fallback_email=email)
        if error:
            conn.rollback()
            return False, error
        
        conn.commit()
        return True, {"track": track, "email": confirm_email}


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
        logger.error("Database error: %s", exc)
        return False, "A database error occurred. Please try again."

    finally:
        mithrix.close()
        conn.close()


# ____________________________sign in or authentication idk_______________________

def sign_in(username, password, device_ip=None):
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    now = datetime.now(timezone.utc)

    try:
        mithrix.execute("""
        SELECT u.user_id, u.locked_until, u.account_status, k.username, r.password AS password_hash,
               ro.role_id, ro.role_name,
               u.user_first_name, u.user_last_name
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

        # start of new sign in with lockout and audit logging (if the bruth force defence is not needed delete the code from here to the end of the next comment)
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
            # Deliberately generic — a differing message here (e.g. "X attempts
            # remaining") would let an attacker infer that this username exists,
            # since non-existent usernames never reach this branch at all.
            return None, "Invalid username or password."

        # Account-status is only disclosed *after* the password has been
        # proven correct — checking it earlier (even for a real username)
        # would let anyone probe account status without knowing the password.
        if row["account_status"] != "active":
            if row["account_status"] == "pending":
                return None, "Account is pending verification. Please wait for approval."
            if row["account_status"] == "rejected":
                return None, "Account registration was rejected. Contact support for help."
            return None, "Account is not allowed to sign in."

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
        logger.error("Database error: %s", exc)
        conn.rollback()
        return None, "Something went wrong while signing in. Please try again."

    finally:
        mithrix.close()
        conn.close()
# end of new sign in with lockout and audit logging


# _______________forgot password stuffs_____________

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
        logger.error("Database error: %s", exc)
        return None, None, "A database error occurred. Please try again."

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
        logger.error("Error: %s", exc)
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
        logger.error("Database error: %s", exc)
        return False, "A database error occurred. Please try again."

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
        logger.error("Database error: %s", exc)
        return False, "A database error occurred. Please try again."

    finally:
        mithrix.close()
        conn.close()

def change_own_password(user_id, current_password, new_password):
    """
    Self-service password change from the User Information page —
    distinct from change_password(), which is reached via the
    forgot-password/OTP flow (proves identity through email instead of
    a known current password). Verifies current_password first, then
    reuses change_password()'s existing swap logic with reset_id=None
    (there's no password_reset row to mark used in this flow).
    """
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        mithrix.execute("""
            SELECT r.password AS password_hash
            FROM slug sl
            JOIN ror r ON r.password_id = sl.password_id
            WHERE sl.user_id = %s AND sl.is_current = TRUE
            LIMIT 1
        """, (user_id,))
        row = mithrix.fetchone()

        if not row or not check_password_hash(row["password_hash"], current_password):
            return False, "Current password is incorrect."
    except Exception as exc:
        logger.error("Database error: %s", exc)
        return False, "A database error occurred. Please try again."
    finally:
        mithrix.close()
        conn.close()

    return change_password(None, user_id, new_password)


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
        logger.error("Database error: %s", exc)
        return False, "A database error occurred. Please try again."

    finally:
        mithrix.close()
        conn.close()
# ______________________________Admin CRUD Operations for Manage Capstone Repository___________________________

def get_pending_verifications():
    """
    Pending account-verification requests (request_type starts with
    'verification_') for the Manage Users > Pending Accounts tab.

    Kept as its own query rather than reused from get_all_requests(),
    since that one INNER JOINs on capstone — verification requests have
    capstone_id = NULL and would silently disappear from that join.
    """
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        mithrix.execute("""
            SELECT r.request_id, r.user_id, r.request_type, r.request_status, r.request_date,
                   CONCAT_WS(' ', u.user_first_name, u.user_middle_name, u.user_last_name) AS full_name,
                   u.university_no,
                   r_role.role_name AS role,
                   c.contact_value AS email
            FROM request r
            JOIN "user" u ON u.user_id = r.user_id
            JOIN role r_role ON r_role.role_id = u.role_id
            LEFT JOIN contact c ON c.user_id = u.user_id AND c.contact_type = 'email' AND c.is_primary = TRUE
            WHERE r.request_type LIKE 'verification_%%'
              AND r.request_status = 'pending'
            ORDER BY r.request_date ASC
        """)
        return mithrix.fetchall()
    except Exception as exc:
        logger.error("Database error: %s", exc)
        return []
    finally:
        mithrix.close()
        conn.close()

def review_verification_request(request_id, decision, status_reason, reviewed_by):
    """
    Approve/reject an account-verification request. Unlike review_request()
    (used for manuscript-access requests), this also flips the underlying
    user's account_status — that's the step that was previously missing
    entirely, leaving approved users stuck on 'pending' forever with no
    way to sign in.

    decision: 'approved' or 'rejected'
    """
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    now = datetime.now(timezone.utc)

    try:
        mithrix.execute("""
            SELECT user_id, request_type FROM request
            WHERE request_id = %s AND request_type LIKE 'verification_%%'
            FOR UPDATE
        """, (request_id,))
        row = mithrix.fetchone()
        if not row:
            conn.rollback()
            return False, "Verification request not found."

        user_id = row["user_id"]

        mithrix.execute("""
            UPDATE request SET
                request_status = %s,
                status_reason = %s,
                reviewed_by = %s,
                decision_date = %s
            WHERE request_id = %s
        """, (decision, status_reason, reviewed_by, now, request_id))

        new_account_status = "active" if decision == "approved" else "rejected"
        mithrix.execute("""
            UPDATE "user" SET account_status = %s
            WHERE user_id = %s
        """, (new_account_status, user_id))

        log_audit(mithrix, reviewed_by, "review_verification_request", "request", request_id,
                   new_values=f"{decision} -> account_status={new_account_status}")

        conn.commit()
        return True, None
    except Exception as exc:
        conn.rollback()
        logger.error("Database error: %s", exc)
        return False, "A database error occurred. Please try again."
    finally:
        mithrix.close()
        conn.close()
