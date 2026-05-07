import re
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash
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

#student auto detection role pattern
STUDENT_PATTERN = re.compile(r'^SUM\d{4}-\d{5}$', re.IGNORECASE)
#son we need the faculty_pattern

#this should detect the role thingy
def detect_role(university_no):
    if STUDENT_PATTERN.match(university_no):
        return 'student'
    
    # To do we still need the faculty else
    return None

#this should get the role from the role table
def get_role_id(mithrix, role_name):
    mithrix.execute("""SELECT role_id FROM role
                       WHERE LOWER(role_name) = LOWER(%s) LIMIT 1""", (role_name,))
    row = mithrix.fetchone()
    return row[0] if row else None


#this be the sign up i think maybe
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