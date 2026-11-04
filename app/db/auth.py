"""
Authentication & account lifecycle: sign up, sign in/out, role
detection & verification, password reset/OTP, and pending-verification
review. Everything that touches the user, kappa, ror, slug, login,
audit, signup, or password_reset tables lives here.
"""
import re
import logging
import secrets
import psycopg2.extras
from datetime import datetime, timedelta, timezone
from app.utils.password_policy import password_error
from app.utils.contact_policy import normalize_phone
from werkzeug.security import generate_password_hash, check_password_hash

from app.db.connection import db_connect
from app.db.audit import log_audit

logger = logging.getLogger(__name__)

# student and faculty auto detection role pattern
STUDENT_PATTERN = re.compile(r'^(?:(?:[SUM]{3})?\d{4}-\d+|[0-9]{10})$', re.IGNORECASE)
PROFESSOR_PATTERN = re.compile(r'^\d{4}$')
ADMIN_PATTERN = re.compile(r'^admin\d{3}$', re.IGNORECASE)

# validation patterns
EMAIL_PATTERN = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_]{3,30}$')

LOCKOUT_THRESHOLD = 5  # number of allowed failed attempts before lockout
LOCKOUT_DURATION = 20  # lockout duration in minutes

OTP_EXPIRY_MINUTES = 4
OTP_MAX_ATTEMPTS = 2
DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_urlsafe(32))


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
    mithrix.execute("""
        UPDATE signup SET status = 'pending', sub_person_type = %s,
            requested_at = CURRENT_TIMESTAMP, decided_at = NULL,
            reviewed_by = NULL, reason = NULL, attempt_count = attempt_count + 1
        WHERE signup_id = (SELECT signup_id FROM signup WHERE user_id = %s
                           ORDER BY signup_id DESC LIMIT 1)
    """, (track, user_id))
    log_audit(mithrix, user_id, "verification_request", "user", user_id)

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

        if role_name == 'Student':
            conn.rollback()
            return False, 'Use explicit rejected-student resubmission with a newly verified email.'

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
    # ProxyFix adjusts this only for an explicitly trusted proxy chain.
    return request.remote_addr

def get_role_id(mithrix, role_name):
    mithrix.execute("""SELECT role_id FROM role
                       WHERE LOWER(role_name) = LOWER(%s) LIMIT 1""", (role_name,))
    row = mithrix.fetchone()
    return row["role_id"] if row else None

def create_user(first_name, middle_name, last_name, university_no, email, username, password, cor_filename=None, preferred_contact="email", phone="", terms_version=None, requested_role=None, signup_verification_id=None, resubmit=False):

    #strip and basic validation
    first_name    = first_name.strip()    if first_name    else ""
    middle_name   = middle_name.strip()   if middle_name   else ""
    last_name     = last_name.strip()     if last_name     else ""
    university_no = (university_no or "").strip().upper()
    email         = email.strip().lower() if email else ""
    username      = username.strip()      if username      else ""
    role_name = requested_role or (detect_role(university_no) if university_no else "Student")

    # validation
    if not all([first_name, last_name, username, password]):
        return False, "All required fields must be filled in."
    if not resubmit and password_error(password):
        return False, password_error(password)
    if resubmit and len(password)>256:
        return False, 'Existing password is too long.'
    try:
        phone = normalize_phone(phone)
    except ValueError as exc:
        return False, str(exc)
    if not email:
        return False, "Enter an email for account recovery."
    if preferred_contact not in ('email', 'phone') or (preferred_contact == 'phone' and not phone):
        return False, "Choose a valid contact preference and supply its contact details."
    if email and not EMAIL_PATTERN.match(email):
        return False, "Invalid email format."
    if not USERNAME_PATTERN.match(username):
        return False, "Username must be 3-30 characters, letters, numbers, and underscores only."

    if role_name not in ("Student", "Faculty"):
        return False, "Choose Student or Faculty as your account type."
    if role_name == 'Student':
        from app.services.roster_import import valid_number
        if not cor_filename:
            return False, 'Upload your COR PDF before submitting a student application.'
        if not valid_number(university_no):
            return False, 'Enter your student number exactly as recorded by the university.'
        if not signup_verification_id:
            return False, 'Verify your email before submitting your student application.'
    elif university_no and detect_role(university_no) != role_name:
        logger.warning(
            "University number '%s' did not match any known patterns.", university_no)
        return False, ("University number format not recognized")

    if resubmit:
        if role_name != 'Student':
            return False, 'Use the existing faculty verification process.'
        return _resubmit_student(first_name, middle_name, last_name, university_no, email,
                                 username, password, cor_filename, signup_verification_id, terms_version)
    password_hash = generate_password_hash(password)
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    now = datetime.now(timezone.utc)

    try:
        from app.db.roster import lock_student_roster, decide_student
        lock_student_roster(mithrix)
        role_id = get_role_id(mithrix, role_name)
        if role_id is None:
            return False, f"Role '{role_name}' is not in the system"

        if signup_verification_id is not None:
            from app.db.signup_verification import consume_email_verification
            mithrix.execute("SELECT pg_advisory_xact_lock(hashtext('signup-email'), hashtext(%s))", (email.lower(),))
            mithrix.execute("SELECT 1 FROM contact WHERE contact_type = 'email' AND LOWER(contact_value) = %s LIMIT 1", (email.lower(),))
            if mithrix.fetchone():
                conn.rollback()
                return False, "An account already uses these details. Sign in, recover your account, or explicitly resubmit a rejected student application."
            if role_name != 'Student' and not consume_email_verification(mithrix, signup_verification_id, email):
                conn.rollback()
                return False, "Verify your email again before creating an account."

        # insert to user table
        insert_university_no = university_no or None
        mithrix.execute("""INSERT INTO "user"
            (role_id, user_first_name, user_middle_name,
            user_last_name, university_no, account_status, cor_filename,
            preferred_contact, terms_version, terms_accepted_at)
            VALUES (%s, %s, %s, %s, %s, 'pending', %s, %s, %s, %s)
            RETURNING user_id
            """, (role_id, first_name, middle_name, last_name, insert_university_no,
                  cor_filename, preferred_contact, terms_version, now if terms_version else None))
        user_id = mithrix.fetchone()["user_id"]

        if phone:
            mithrix.execute("INSERT INTO contact (user_id, contact_type, contact_value, is_primary, created_at) VALUES (%s, 'phone', %s, TRUE, %s)",
                            (user_id, phone, now))

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
        """, (password_hash, now))
        password_id = mithrix.fetchone()["password_id"]

        # insert the owner
        mithrix.execute("""INSERT INTO slug
            (username_id, password_id, user_id,
            assigned_at, updated_at, is_current)
            VALUES (%s, %s, %s, %s, %s, TRUE)
        """, (username_id, password_id, user_id, now, now))

        # insert contact
        if email:
            mithrix.execute("""INSERT INTO contact
                (user_id, contact_type, contact_value,
                is_primary, created_at)
                VALUES (%s, 'email', %s, TRUE, %s) RETURNING contact_id
            """, (user_id, email.lower(), now))
            email_contact_id = mithrix.fetchone()['contact_id']

        # add log to sign up tble
        mithrix.execute("""
            INSERT INTO signup (user_id, registration_date, requested_at, status, contact_id, method)
            VALUES (%s, %s, %s, 'pending', %s, %s)
            RETURNING signup_id
        """, (user_id, now, now, email_contact_id, 'auto' if role_name == 'Student' else 'manual'))
        signup_id = mithrix.fetchone()["signup_id"]

        log_audit(mithrix, user_id, "signup", "signup", signup_id)

        if role_name == 'Student':
            decision = decide_student(mithrix, user_id, signup_id, university_no, email, email_contact_id, signup_verification_id)
            conn.commit()
            return True, {'track': 'student', 'email': email, 'decision': decision, 'signup_id': signup_id}


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
            msg = "An account already uses these details. Sign in, recover your account, or explicitly resubmit a rejected student application."
        else:
            msg = "A duplicate-entry error occurred."
        return False, msg

    except Exception as exc:
        conn.rollback()
        logger.error('Account creation failed (%s)',type(exc).__name__)
        return False, "A database error occurred. Please try again."

    finally:
        mithrix.close()
        conn.close()


# ____________________________sign in or authentication idk_______________________

def _resubmit_student(first, middle, last, number, email, username, password, cor_filename, proof, terms_version):
    """Authenticated explicit retry; preserve identity, credentials and decision history."""
    from app.db.roster import lock_student_roster, decide_student
    conn = db_connect()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        lock_student_roster(cursor)
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext('signup-email'),hashtext(%s))",(email,))
        cursor.execute('''SELECT u.user_id,u.university_no,p.password,c.contact_id FROM "user" u
            JOIN role r USING(role_id) JOIN slug s ON s.user_id=u.user_id AND s.is_current
            JOIN kappa k USING(username_id) JOIN ror p USING(password_id)
            JOIN contact c ON c.user_id=u.user_id AND c.contact_type='email' AND c.is_primary
            WHERE k.username=%s AND u.account_status='rejected' AND r.role_name='Student'
            AND LOWER(BTRIM(c.contact_value))=%s FOR UPDATE OF u''',(username,email))
        account = cursor.fetchone()
        if not account or not check_password_hash(account['password'],password):
            conn.rollback()
            return False,'Could not resubmit. Check your existing credentials and verified email, or use account recovery.'
        user_id = account['user_id']
        cursor.execute('''UPDATE "user" SET account_status='pending',user_first_name=%s,user_middle_name=%s,
            user_last_name=%s,cor_filename=%s,university_no=%s,terms_version=COALESCE(%s,terms_version),
            terms_accepted_at=CASE WHEN %s::text IS NOT NULL THEN CURRENT_TIMESTAMP ELSE terms_accepted_at END
            WHERE user_id=%s''',(first,middle,last,cor_filename,number,terms_version,terms_version,user_id))
        cursor.execute('''INSERT INTO signup(user_id,registration_date,requested_at,status,method,contact_id)
            VALUES(%s,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,'pending','auto',%s) RETURNING signup_id''',(user_id,account['contact_id']))
        signup_id = cursor.fetchone()['signup_id']
        log_audit(cursor,user_id,'student_resubmission','signup',signup_id,
                  old_values=account['university_no'],new_values=number)
        decision = decide_student(cursor,user_id,signup_id,number,email,account['contact_id'],proof)
        conn.commit()
        return True,{'track':'student','email':email,'decision':decision,'signup_id':signup_id}
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return False,'An account already uses these details. Use sign-in/recovery or contact your verifier to correct the identity.'
    except Exception as exc:
        conn.rollback()
        logger.error('Student resubmission failed (%s)',type(exc).__name__)
        return False,'Could not resubmit. Try again later or contact your verifier.'
    finally:
        cursor.close()
        conn.close()


def sign_in(username, password, device_ip=None):
    if not isinstance(username, str) or not isinstance(password, str) or len(username) > 30 or len(password) > 1024:
        return None, "Invalid username or password."
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    now = datetime.now(timezone.utc)

    try:
        mithrix.execute("""
        SELECT u.user_id, u.account_status, k.username, r.password AS password_hash, sl.password_id,
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
            check_password_hash(DUMMY_PASSWORD_HASH, password)
            return None, "Invalid username or password."

        if not check_password_hash(row["password_hash"], password):

            mithrix.execute("""
                INSERT INTO login (user_id, log_in_time, login_device_ip, failed_attempts)
                VALUES (%s, %s, %s, 1)
                RETURNING log_in_id
            """, (row["user_id"], now, device_ip))

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
            INSERT INTO login (user_id, log_in_time, login_device_ip, failed_attempts)
            VALUES (%s, %s, %s, 0)
            RETURNING log_in_id
        """, (user_id, now, device_ip))
        log_in_id = mithrix.fetchone()["log_in_id"]

        log_audit(mithrix, user_id, "login", "login", log_in_id)

        conn.commit()

        return {
            "user_id":         user_id,
            "password_id":     row["password_id"],
            "username":        row["username"],
            "role_id":         row["role_id"],
            "role_name":       row["role_name"],
            "user_first_name": row["user_first_name"],
            "user_last_name":  row["user_last_name"],
            "log_in_id":       log_in_id,
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

def lookup_phone_for_reset(user_id):
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        mithrix.execute("""
            SELECT contact_id, contact_value FROM contact
            WHERE user_id = %s AND contact_type = 'phone' AND is_primary = TRUE
            ORDER BY contact_id LIMIT 1
        """, (user_id,))
        return mithrix.fetchone()
    except Exception:
        raise RuntimeError('Could not look up the recovery phone.') from None
    finally:
        mithrix.close()
        conn.close()


def create_otp(contact_id, expected_destination=None):
    otp = f"{secrets.randbelow(1000000):06d}"

    conn = db_connect()
    mithrix = conn.cursor()
    now = datetime.now(timezone.utc)
    expiry = now.replace(second=now.second)

    from datetime import timedelta
    expiry = now + timedelta(minutes=OTP_EXPIRY_MINUTES)

    try:
        mithrix.execute('''SELECT u.user_id FROM "user" u JOIN contact c ON c.user_id = u.user_id
                           WHERE c.contact_id = %s FOR UPDATE OF u''', (contact_id,))
        if not mithrix.fetchone():
            raise ValueError('Recovery contact unavailable.')
        mithrix.execute('SELECT contact_value FROM contact WHERE contact_id = %s FOR UPDATE', (contact_id,))
        contact = mithrix.fetchone()
        if not contact or (expected_destination is not None and contact[0] != expected_destination):
            raise ValueError('Recovery contact changed. Start again.')
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
        raise RuntimeError("Could not create OTP.") from exc

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
            FOR UPDATE
        """, (reset_id,))
        row = mithrix.fetchone()

        if not row:
            return False, "invalid reset token"
        now = datetime.now(timezone.utc)
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

        mithrix.execute("UPDATE password_reset SET verified_at = %s WHERE reset_id = %s", (now, reset_id))
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

def change_password(reset_id, user_id, new_password, current_password=None):
    if password_error(new_password):
        return False, password_error(new_password)

    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    now = datetime.now(timezone.utc)

    try:
        mithrix.execute('SELECT user_id FROM "user" WHERE user_id = %s FOR UPDATE', (user_id,))
        if not mithrix.fetchone():
            return False, "Account not found."
        now = datetime.now(timezone.utc)
        if reset_id is not None:
            mithrix.execute("""
                SELECT pr.reset_id FROM password_reset pr
                JOIN contact c ON c.contact_id = pr.contact_id
                WHERE pr.reset_id = %s AND c.user_id = %s
                  AND pr.is_used = FALSE AND pr.verified_at IS NOT NULL
                  AND pr.expiry_date > %s
                FOR UPDATE OF pr
            """, (reset_id, user_id, now))
            if not mithrix.fetchone():
                return False, "Reset expired or already used. Please start again."
        else:
            mithrix.execute("""
                SELECT r.password FROM slug sl JOIN ror r ON r.password_id = sl.password_id
                WHERE sl.user_id = %s AND sl.is_current = TRUE
            """, (user_id,))
            credential = mithrix.fetchone()
            if (not credential or not isinstance(current_password, str) or len(current_password) > 1024
                    or not check_password_hash(credential['password'], current_password)):
                return False, "Current password is incorrect."
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
            WHERE contact_id IN (SELECT contact_id FROM contact WHERE user_id = %s)
        """, (user_id,))

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
    """Check the current credential and swap it in one locked transaction."""
    return change_password(None, user_id, new_password, current_password=current_password)


def sign_out(user_id, device_ip=None):
    conn = db_connect()
    mithrix = conn.cursor()

    try:
        log_audit(
            mithrix, user_id,
            "logout", "user", user_id,
            old_values=None,
            new_values=device_ip
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

def get_pending_verifications(reviewed_by=None):
    """Pending account verification uses the approved signup review fields."""
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        from app.db.verification_documents import STUDENT_REVIEW_SQL,reviewer_owner
        owner=reviewer_owner(mithrix,reviewed_by) if reviewed_by is not None else None
        student_scope=STUDENT_REVIEW_SQL if owner is not None else STUDENT_REVIEW_SQL.replace('AND (%s::int IS NULL OR master.uploader_user_id=%s)','')
        if owner is None:
            student_scope=f"({student_scope}) OR COALESCE(r.status,u.account_status)='pending'"
        mithrix.execute(f"""
            SELECT r.signup_id AS request_id, r.user_id, r.sub_person_type AS request_type,
                   COALESCE(r.status, u.account_status) AS request_status,
                   COALESCE(r.requested_at, r.registration_date) AS request_date,
                   CONCAT_WS(' ', u.user_first_name, u.user_middle_name, u.user_last_name) AS full_name,
                   u.university_no,
                   r_role.role_name AS role,
                   c.contact_value AS email,r.reason AS verification_reason
            FROM signup r
            JOIN "user" u ON u.user_id = r.user_id
            JOIN role r_role ON r_role.role_id = u.role_id
            LEFT JOIN contact c ON c.user_id = u.user_id AND c.contact_type = 'email' AND c.is_primary = TRUE
            WHERE (r_role.role_name<>'Student' AND COALESCE(r.status,u.account_status)='pending')
                OR (r_role.role_name='Student' AND ({student_scope}))
            ORDER BY r.requested_at ASC
        """,(owner,owner) if owner is not None else ())
        return mithrix.fetchall()
    except Exception as exc:
        logger.error("Database error: %s", exc)
        return []
    finally:
        mithrix.close()
        conn.close()

def get_verification_request_recipient(request_id):
    conn = db_connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute('''
                SELECT CONCAT_WS(' ', u.user_first_name, u.user_middle_name, u.user_last_name) AS full_name,
                       c.contact_value AS email
                FROM signup r JOIN "user" u ON u.user_id = r.user_id
                LEFT JOIN contact c ON c.user_id = u.user_id
                    AND c.contact_type = 'email' AND c.is_primary = TRUE
                WHERE r.signup_id = %s AND COALESCE(r.status, u.account_status) IN ('pending','rejected')
                ORDER BY c.contact_id LIMIT 1
            ''', (request_id,))
            return cursor.fetchone()
    except Exception:
        logger.exception('Could not look up verification email recipient')
        return None
    finally:
        conn.close()


def review_verification_request(request_id, decision, status_reason, reviewed_by):
    """Review a pending signup and update account status atomically."""
    status_reason = (status_reason or '').strip()
    if decision not in ('approved', 'rejected'):
        return False, "Invalid decision."
    if len(status_reason) > 2000 or (decision == 'rejected' and not status_reason):
        return False, "Provide a rejection reason of 1-2000 characters."
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    now = datetime.now(timezone.utc)

    try:
        from app.db.roster import lock_student_roster
        from app.db.verification_documents import reviewer_owner
        lock_student_roster(mithrix)
        owner=reviewer_owner(mithrix,reviewed_by)
        mithrix.execute("""
            SELECT s.user_id,COALESCE(s.status,u.account_status) AS status,s.method,s.reason,s.contact_id,r.role_name,u.university_no,u.cor_filename
            FROM signup s JOIN "user" u ON u.user_id = s.user_id
            LEFT JOIN role r ON r.role_id=u.role_id
            WHERE s.signup_id = %s AND COALESCE(s.status, u.account_status) IN ('pending','rejected')
              AND u.account_status IN ('pending','rejected')
              AND NOT EXISTS (SELECT 1 FROM signup newer WHERE newer.user_id=s.user_id AND newer.signup_id>s.signup_id)
              AND NOT EXISTS (SELECT 1 FROM signup approved WHERE approved.user_id=s.user_id AND approved.status='approved')
            FOR UPDATE OF s,u
        """, (request_id,))
        row = mithrix.fetchone()
        if not row:
            conn.rollback()
            return False, "Verification request not found."

        roster_id=None
        if row['role_name']=='Student':
            if row['status']=='rejected' and row['method']!='auto':
                conn.rollback()
                return False,'This application has already been manually reviewed.'
            mithrix.execute('''SELECT matched.roster_id,master.uploader_user_id FROM roster matched
                JOIN uploaded_by master USING(upload_id) WHERE matched.person_type='Student' AND master.status='active'
                AND UPPER(BTRIM(matched.university_no))=UPPER(BTRIM(%s)) ORDER BY matched.roster_id
                FOR UPDATE OF matched,master''',(row['university_no'],))
            matches=mithrix.fetchall()
            owned=[match for match in matches if owner is None or match['uploader_user_id']==owner]
            if not owned and (owner is not None or decision=='approved'):
                conn.rollback()
                return False,'Student number does not match an active masterlist you manage.'
            if decision=='approved':
                if len(matches)!=1 or not row['cor_filename']:
                    conn.rollback()
                    return False,'Approval requires a COR and one unique active masterlist match.'
                mithrix.execute('''SELECT 1 FROM contact c
                    WHERE c.contact_id=%s AND c.user_id=%s AND c.contact_type='email'
                    AND (EXISTS (SELECT 1 FROM signup_email_verifications proof
                        WHERE proof.email=LOWER(BTRIM(c.contact_value)) AND proof.verified_at IS NOT NULL AND proof.consumed_at IS NOT NULL)
                        OR EXISTS (SELECT 1 FROM audit evidence WHERE evidence.user_id=c.user_id
                            AND evidence.action_type='automatic_signup_decision' AND evidence.affected_table='signup'
                            AND evidence.affected_record_id=%s)) LIMIT 1''',(row['contact_id'],row['user_id'],request_id))
                if not mithrix.fetchone():
                    conn.rollback()
                    return False,'Student must verify their email and resubmit before approval.'
                roster_id=matches[0]['roster_id']
                mithrix.execute("SELECT 1 FROM signup WHERE roster_id=%s AND signup_id<>%s AND status IN ('pending','approved')",(roster_id,request_id))
                if mithrix.fetchone():
                    conn.rollback()
                    return False,'This masterlist identity is already claimed or reserved.'
        elif row['status']!='pending':
            conn.rollback()
            return False,'Verification request not found.'

        user_id = row["user_id"]

        mithrix.execute("""
            UPDATE signup SET
                status = %s,
                reason = %s,
                reviewed_by = %s,
                decided_at = %s,
                method = CASE WHEN %s THEN 'manual' ELSE method END,
                roster_id = COALESCE(%s,roster_id)
            WHERE signup_id = %s
        """, (decision, status_reason, reviewed_by, now,row['role_name']=='Student',roster_id,request_id))

        new_account_status = "active" if decision == "approved" else "rejected"
        mithrix.execute("""
            UPDATE "user" SET account_status = %s
            WHERE user_id = %s
        """, (new_account_status, user_id))

        log_audit(mithrix, reviewed_by, "review_verification_request", "signup", request_id,
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
