import re
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config

#connection and stuff
def db_connect():
    conn = psycopg2.connect(
        host=Config.PG_HOST,
        port=Config.PG_PORT,
        user=Config.PG_USER,
        password=Config.PG_PASSWORD,
        database=Config.PG_DB,
    )

    return conn

#student and faculty auto detection role pattern
STUDENT_PATTERN = re.compile(r'^SUM\d{4}-\d{5}$', re.IGNORECASE)
PROFESSOR_PATTERN = re.compile(r'^\d{4}$')

#this should detect the role thingy
def detect_role(university_no):
    if STUDENT_PATTERN.match(university_no):
        return "student"
    if PROFESSOR_PATTERN.match(university_no):
        return "faculty"
    #if needed we can add more roles to auto assign
    return None

#_____________________________________helper functions gang_______________________________ ps i was getting lost in the code so therese allat of notes now
def get_role_id(mithrix, role_name):
    mithrix.execute("""SELECT role_id FROM role
                       WHERE LOWER(role_name) = LOWER(%s) LIMIT 1""", (role_name,))
    row = mithrix.fetchone()
    return row[0] if row else None

def log_audit(mithrix, user_id, action_type, affected_table, affected_record_id):
    mithrix.execute("""
        INSERT INTO audit
        (user_id, action_type, affected_table, affected_record_id, action_timestamp)
        VALUES (%s, %s, %s, %s, %s)
    """, (user_id, action_type, affected_table, affected_record_id, datetime.now(timezone.utc)))


#___________________________________this be the sign up i think maybe______________________________
def create_user(first_name, middle_name, last_name, university_no, email, username, password):

    role_name = detect_role(university_no)
    if role_name is None:
        return False, ("University number format not recognized")
    
    conn = db_connect()
    mithrix = conn.cursor()
    now = datetime.now(timezone.utc)

    try:
        role_id = get_role_id(mithrix, role_name)
        if role_id is None:
            return False, f"Role '{role_name}' is not in the system"
        
        #insert to user table
        mithrix.execute("""INSERT INTO "user"
            (role_id, user_first_name, user_middle_name,
            user_last_name, university_no)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING user_id
            """,(role_id, first_name, middle_name, last_name, university_no))
        user_id = mithrix.fetchone()[0]

        #insert into username table
        mithrix.execute("""INSERT INTO kappa (username)
            VALUES (%s)
            RETURNING username_id
        """,(username,))
        username_id = mithrix.fetchone()[0]

        #insert you know what
        mithrix.execute("""INSERT INTO ror (password, updated_at, previous_password_id)
            VALUES (%s, %s, NULL)
            RETURNING password_id
        """,(generate_password_hash(password), now))
        password_id = mithrix.fetchone()[0]

        #insert the owner 
        mithrix.execute("""INSERT INTO slug
            (username_id, password_id, user_id,
            assigned_at, updated_at, is_current)
            VALUES (%s, %s, %s, %s, %s, TRUE)
        """,(username_id, password_id, user_id, now, now))

        #insert contact
        mithrix.execute("""INSERT INTO contact
            (user_id, contact_type, contact_value,
            is_primary, created_at)
            VALUES (%s, 'email', %s, TRUE, %s)
        """,(user_id, email.lower(), now))

        #insert to signup
        mithrix.execute("""INSERT INTO signup (user_id, registration_date)
            VALUES (%s, %s)
        """,(user_id, now))

        #add log to sign up tble
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
        if "kappa"       in detail or "username"      in detail:
            msg = "That username is already taken."
        elif "contact"   in detail or "contact_value" in detail:
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

#____________________________sign in or authentication idk_______________________
def sign_in(username, password, device_ip=None):
    conn = db_connect()
    mithrix = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    now = datetime.now(timezone.utc)

    try:
        mithrix.execute("""
        SELECT u.user_id, k.username, r.password AS password_hash, ro.role_id, ro.role_name
        FROM kappa k
        JOIN slug sl ON sl.username_id = k.username_id AND sl.is_current = TRUE
        JOIN ror   r  ON r.password_id  = sl.password_id
        JOIN "user" u ON u.user_id      = sl.user_id
        JOIN role  ro ON ro.role_id     = u.role_id
        WHERE k.username = %s
        LIMIT 1
    """,(username,))
        
        row = mithrix.fetchone()

        if not row:
            return None, "username not found"
        
        if not check_password_hash(row["password_hash"], password):
            return None, "incorect password"
        
        user_id = row["user_id"]

        mithrix.execute("""
            INSERT INTO login (user_id, log_in_time, login_device_ip)
            VALUES(%s, %s, %s)
            RETURNING log_in_id
        """, (user_id, now, device_ip))
        log_in_id = mithrix.fetchone()["log_in_id"]

        log_audit(mithrix, user_id, "login", "login", log_in_id)

        conn.commit()

        return{
            "user_id": user_id,
            "username": row["username"],
            "role_id": row["role_id"],
            "role_name": row["role_name"],
        }, None

    except Exception as exc:
        conn.rollback()
        return None, f"Database error: {exc}"
    
    finally:
        mithrix.close()
        conn.close()