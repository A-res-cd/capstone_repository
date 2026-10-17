"""
data_seeder_current.py — Copy of data_seeder.py for the current CAPRE schema.

Populates the schema shown in the ERD with:
  1. Reference/lookup data you specified as pre-inserted:
       role:           Student, Faculty, Admin, Capstone Professor
       specialization: DST, NST, WST, GENERAL
       program:        BSIT, BSDS
  2. A handful of sample users across every role, created through the
     exact same insert chain create_user() uses (user -> kappa -> ror
     -> slug -> contact -> signup -> audit), so seeded accounts behave
     identically to real signups and can actually log in.
  3. Sample keywords, capstones, authors/advisers, and manuscript
     requests so the repository/archive/requests pages have real data
     to render against during development.

Usage:
    python scripts/data_seeder_current.py               # seed 100 capstones
    python scripts/data_seeder_current.py --count 25
    python scripts/data_seeder_current.py --reseed       # truncate ALL data, then seed
    python scripts/data_seeder_current.py --truncate     # truncate ALL data and exit
    python scripts/data_seeder_current.py --users-only
    python scripts/data_seeder_current.py --capstones-only

Apply database/capre_original_final.sql or the current migrations first.
Manuscript paths are placeholders; this script does not create sample PDFs.
Rate-limit buckets and email-verification challenges are left empty.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import argparse
import os
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash

from config import Config
from app.constants.roles import ROLE_ADMIN
from app.db.keywords import set_capstone_keywords
from app.db.capstone_requests import record_capstone_request


BASE_DIR = ROOT
UPLOAD_FOLDER_DEFAULTS = {
    "UPLOAD_MANUSCRIPT_FOLDER": "instance/uploads/manuscripts",
    "UPLOAD_REGISTRATION_FOLDER": "instance/uploads/registration",
    "UPLOAD_AVATAR_FOLDER": "instance/uploads/avatars",
}


def configured_upload_folder(setting_name):
    """Resolve an upload folder the same way the app expects it."""
    configured = os.environ.get(setting_name) or UPLOAD_FOLDER_DEFAULTS[setting_name]
    path = Path(configured)
    return path if path.is_absolute() else BASE_DIR / path


def prepare_upload_folders():
    """Create private upload folders without moving or overwriting files."""
    for setting_name in UPLOAD_FOLDER_DEFAULTS:
        configured_upload_folder(setting_name).mkdir(parents=True, exist_ok=True)


def manuscript_storage_key(filename):
    """Store only a logical filename, never a machine-specific path."""
    filename = str(filename).replace("\\", "/")
    return f"uploads/{Path(filename).name}"


# ──────────────────────────────────────────────────────────────────
# Connection
# ──────────────────────────────────────────────────────────────────

def db_connect():
    return psycopg2.connect(
        host=Config.PG_HOST,
        port=Config.PG_PORT,
        user=Config.PG_USER,
        password=Config.PG_PASSWORD,
        database=Config.PG_DB,
        sslmode=Config.PG_SSLMODE,
        connect_timeout=Config.PG_CONNECT_TIMEOUT,
    )


# ──────────────────────────────────────────────────────────────────
# Reference data (pre-inserted lookups)
# ──────────────────────────────────────────────────────────────────

ROLES = [
    # (role_name, role_level) — role_level isn't read anywhere in the
    # app's authorization logic (which uses role names), but it's
    # seeded for completeness. Match current role IDs on fresh databases.
    ("Student", 1),
    ("Faculty", 2),
    (ROLE_ADMIN, 3),
    ("Capstone Professor", 2),
]

PROGRAMS = [
    "BSIT",
    "BSDS",
]

SPECIALIZATIONS = [
    "DST",
    "NST",
    "WST",
    "GENERAL",
]

PROGRAM_NAMES = {
    "BSIT": "Bachelor of Science in Information Technology",
    "BSDS": "Bachelor of Science in Data Science",
}
SPECIALIZATION_NAMES = {
    "DST": "Database Systems Technology",
    "NST": "Network Systems Technology",
    "WST": "Web Systems Technology",
    "GENERAL": "No specialization",
}


# ──────────────────────────────────────────────────────────────────
# Sample users
# University numbers must match the regex patterns in app/db/database.py:
#   STUDENT_PATTERN   ^2\d{9}$ | ^2\d{3}-\d{5}$ | ^[A-Z]{2,4}\d{4}-\d{5}$
#   PROFESSOR_PATTERN ^\d{4}$
#   ADMIN_PATTERN     ^admin\d{3}$
# "Capstone Professor" isn't assigned automatically by detect_role() —
# it's a role an Admin assigns manually via update_user_role(), so
# those seeded users start as Faculty-pattern numbers and get their
# role_id pointed at "Capstone Professor" directly in the insert.
# ──────────────────────────────────────────────────────────────────

SAMPLE_USERS = [
    # role_name,            first,     middle,   last,        university_no,    email,                         username,        password
    ("Student",             "Maria",   "Santos",  "Cruz",      "2021-00123",     "maria.cruz@student.edu",      "mcruz",         "password123"),
    ("Student",             "Juan",    "Dela",    "Reyes",     "2021-00456",     "juan.reyes@student.edu",      "jreyes",        "password123"),
    ("Student",             "Ana",     "Lopez",   "Garcia",    "2022-00789",     "ana.garcia@student.edu",      "agarcia",       "password123"),
    ("Faculty",             "Roberto", "Ignacio", "Bautista",  "1042",           "r.bautista@faculty.edu",      "rbautista",     "password123"),
    ("Faculty",             "Liza",    "Mae",     "Fernandez", "1077",           "l.fernandez@faculty.edu",     "lfernandez",    "password123"),
    ("Capstone Professor",  "Carlos",  "Miguel",  "Torres",    "1099",           "c.torres@faculty.edu",        "ctorres",       "password123"),
    (ROLE_ADMIN,             "Admin",   "",        "User",      "admin001",       "admin@capstonerepo.edu",      "admin",         "admin123456"),
    (ROLE_ADMIN,             "System",  "",        "Administrator", None,           "sysadmin@capstonerepo.edu",   "sysadmin",      "sysadmin123456"),
]


# ──────────────────────────────────────────────────────────────────
# Sample keywords + capstones
# capstone.term is in the schema but isn't populated or read anywhere
# in the application's UI today (see BUGS.md #7), so it's left NULL
# here, same as real records created through the app would have it.
# ──────────────────────────────────────────────────────────────────

SAMPLE_CAPSTONES = [
    # keywords, specialization, program, title, year, file, semester
    (
        "machine learning, fraud detection, neural networks",
        "DST",
        "BSIT",
        "Fraud Detection in Financial Transactions Using Deep Learning",
        2024,
        "sample_capstone_1.pdf",
        "1st",
    ),
    (
        "network security, intrusion detection, IoT",
        "NST",
        "BSIT",
        "An Intrusion Detection System for IoT Networks in Smart Homes",
        2024,
        "sample_capstone_2.pdf",
        "2nd",
    ),
    (
        "web development, accessibility, e-commerce",
        "WST",
        "BSIT",
        "Accessible E-Commerce Platform Design for Visually Impaired Users",
        2023,
        "sample_capstone_3.pdf",
        "1st",
    ),
    (
        "data mining, sentiment analysis, social media",
        "DST",
        "BSIT",
        "Sentiment Analysis of Filipino-Language Social Media Posts",
        2023,
        "sample_capstone_4.pdf",
        "2nd",
    ),
    (
        "responsive design, progressive web apps, performance optimization",
        "WST",
        "BSIT",
        "Performance Optimization Techniques for Progressive Web Applications",
        2025,
        "sample_capstone_5.pdf",
        "1st",
    ),
]

DEFAULT_CAPSTONE_COUNT = 100


def build_sample_capstones(record_count):
    """Return deterministic, unique capstone rows up to record_count."""
    capstones = list(SAMPLE_CAPSTONES[:record_count])
    template_count = len(SAMPLE_CAPSTONES)

    for idx in range(template_count, record_count):
        keywords, specialization, program, title, _, file_path, _ = (
            SAMPLE_CAPSTONES[idx % template_count]
        )
        variant = (idx // template_count) + 1
        capstones.append(
            (
                f"{keywords}, capre seed {idx + 1}",
                specialization,
                program,
                f"{title} (Study {variant:02d})",
                2021 + (idx % 5),
                file_path,
                "1st" if idx % 2 == 0 else "2nd",
            )
        )

    return capstones

# capstone index (0-based, matching SAMPLE_CAPSTONES above) -> authors/adviser
SAMPLE_CAPSTONE_PEOPLE = {
    0: {
        "authors": [
            {"first": "Maria", "middle": "Santos", "last": "Cruz"},
            {"first": "Juan", "middle": "Dela", "last": "Reyes"},
        ],
        "adviser": {"first": "Roberto", "middle": "Ignacio", "last": "Bautista"},
    },
    1: {
        "authors": [
            {"first": "Ana", "middle": "Lopez", "last": "Garcia"},
        ],
        "adviser": {"first": "Liza", "middle": "Mae", "last": "Fernandez"},
    },
    2: {
        "authors": [
            {"first": "Maria", "middle": "Santos", "last": "Cruz"},
        ],
        "adviser": {"first": "Carlos", "middle": "Miguel", "last": "Torres"},
    },
    3: {
        "authors": [
            {"first": "Juan", "middle": "Dela", "last": "Reyes"},
            {"first": "Ana", "middle": "Lopez", "last": "Garcia"},
        ],
        "adviser": {"first": "Roberto", "middle": "Ignacio", "last": "Bautista"},
    },
    4: {
        "authors": [
            {"first": "Ana", "middle": "Lopez", "last": "Garcia"},
        ],
        "adviser": {"first": "Liza", "middle": "Mae", "last": "Fernandez"},
    },
}

# (requester username, capstone index, status, reason)
SAMPLE_REQUESTS = [
    ("mcruz", 1, "pending", "Need this for a related literature review on IoT security."),
    ("jreyes", 2, "approved", "Researching accessibility patterns for a class project."),
    ("agarcia", 0, "rejected", "Insufficient justification provided for full-manuscript access."),
]


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────

def log_audit(cur, user_id, action_type, affected_table, affected_record_id):
    """Mirrors app/db/database.py's log_audit so seeded rows leave the
    same audit trail real actions would."""
    cur.execute(
        """
        INSERT INTO audit
        (user_id, action_type, affected_table, affected_record_id, old_values, new_values, action_timestamp)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (user_id, action_type, affected_table, affected_record_id, None, None, datetime.now(timezone.utc)),
    )


def get_or_create_role(cur, role_name, role_level):
    cur.execute('SELECT role_id FROM role WHERE LOWER(role_name) = LOWER(%s)', (role_name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        'INSERT INTO role (role_name, role_level) VALUES (%s, %s) RETURNING role_id',
        (role_name, role_level),
    )
    return cur.fetchone()[0]


def get_or_create_program(cur, program_name):
    name = PROGRAM_NAMES.get(program_name, program_name)
    cur.execute('SELECT program_id FROM program WHERE LOWER(program_code) = LOWER(%s) OR LOWER(program_name) IN (LOWER(%s), LOWER(%s)) ORDER BY program_id LIMIT 1',
                (program_name, name, program_name))
    row = cur.fetchone()
    if row:
        cur.execute('UPDATE program SET program_code = %s WHERE program_id = %s AND program_code IS NULL',
                    (program_name, row[0]))
        return row[0]
    cur.execute(
        'INSERT INTO program (program_name, program_code) VALUES (%s, %s) RETURNING program_id',
        (name, program_name),
    )
    return cur.fetchone()[0]


def get_or_create_specialization(cur, specialization_name):
    name = SPECIALIZATION_NAMES.get(specialization_name, specialization_name)
    cur.execute(
        'SELECT specialization_id FROM specialization WHERE LOWER(specialization_code) = LOWER(%s) OR LOWER(specialization_name) IN (LOWER(%s), LOWER(%s)) ORDER BY specialization_id LIMIT 1',
        (specialization_name, name, specialization_name),
    )
    row = cur.fetchone()
    if row:
        cur.execute('UPDATE specialization SET specialization_code = %s WHERE specialization_id = %s AND specialization_code IS NULL',
                    (specialization_name, row[0]))
        return row[0]
    cur.execute(
        'INSERT INTO specialization (specialization_name, specialization_code) VALUES (%s, %s) RETURNING specialization_id',
        (name, specialization_name),
    )
    return cur.fetchone()[0]


def get_role_id_by_name(cur, role_name):
    cur.execute('SELECT role_id FROM role WHERE LOWER(role_name) = LOWER(%s)', (role_name,))
    row = cur.fetchone()
    return row[0] if row else None


def get_user_id_by_username(cur, username):
    cur.execute(
        """
        SELECT u.user_id
        FROM "user" u
        JOIN slug s ON s.user_id = u.user_id AND s.is_current = TRUE
        JOIN kappa k ON k.username_id = s.username_id
        WHERE LOWER(k.username) = LOWER(%s)
        """,
        (username,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def get_author_id(cur, first, middle, last):
    """Find an existing author row by name, or None."""
    cur.execute(
        """
        SELECT author_id FROM "author"
        WHERE LOWER(aut_first_name) = LOWER(%s)
          AND LOWER(aut_last_name) = LOWER(%s)
          AND COALESCE(LOWER(aut_middle_name), '') = COALESCE(LOWER(%s), '')
        """,
        (first, last, middle or None),
    )
    row = cur.fetchone()
    return row[0] if row else None


# ──────────────────────────────────────────────────────────────────
# Seed steps
# ──────────────────────────────────────────────────────────────────

def seed_lookups(cur):
    print("Seeding roles, programs, specializations...")
    for role_name, role_level in ROLES:
        get_or_create_role(cur, role_name, role_level)
    for program_name in PROGRAMS:
        get_or_create_program(cur, program_name)
    for spec_name in SPECIALIZATIONS:
        get_or_create_specialization(cur, spec_name)
    print(f"  -> {len(ROLES)} roles, {len(PROGRAMS)} programs, {len(SPECIALIZATIONS)} specializations ready.")


def seed_users(cur):
    print("Seeding sample users...")

    created = 0
    for role_name, first, middle, last, univ_no, email, username, password in SAMPLE_USERS:
        existing = get_user_id_by_username(cur, username)
        if existing:
            print(f"  -- skipping {username} (already exists)")
            continue

        role_id = get_role_id_by_name(cur, role_name)
        if role_id is None:
            print(f"  !! role '{role_name}' not found, skipping user {username}")
            continue

        now = datetime.now(timezone.utc)

        cur.execute(
            """
            INSERT INTO "user"
                (role_id, user_first_name, user_middle_name, user_last_name,
                 university_no, account_status)
            VALUES (%s, %s, %s, %s, %s, 'active')
            RETURNING user_id
            """,
            (role_id, first, middle, last, univ_no),
        )
        user_id = cur.fetchone()[0]

        cur.execute(
            'INSERT INTO kappa (username) VALUES (%s) RETURNING username_id',
            (username,),
        )
        username_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO ror (password, updated_at, previous_password_id)
            VALUES (%s, %s, NULL)
            RETURNING password_id
            """,
            (generate_password_hash(password), now),
        )
        password_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO slug
                (username_id, password_id, user_id, assigned_at, updated_at, is_current)
            VALUES (%s, %s, %s, %s, %s, TRUE)
            """,
            (username_id, password_id, user_id, now, now),
        )

        cur.execute(
            """
            INSERT INTO contact (user_id, contact_type, contact_value, is_primary, created_at)
            VALUES (%s, 'email', %s, TRUE, %s)
            """,
            (user_id, email.lower(), now),
        )

        cur.execute(
            'INSERT INTO signup (user_id, registration_date) VALUES (%s, %s) RETURNING signup_id',
            (user_id, now),
        )
        signup_id = cur.fetchone()[0]

        log_audit(cur, user_id, "signup", "signup", signup_id)

        created += 1
        print(f"  -> created {username} ({role_name}) — login with username='{username}' password='{password}'")

    print(f"  -> {created} user(s) created, {len(SAMPLE_USERS) - created} skipped.")


def seed_capstones(cur, record_count=DEFAULT_CAPSTONE_COUNT):
    print("Seeding sample keywords and capstones...")
    created = 0
    capstone_ids = {}  # index in SAMPLE_CAPSTONES -> capstone_id
    capstones = build_sample_capstones(record_count)

    for idx, (keywords, spec_name, program_name, title, year, file_path, semester) in enumerate(capstones):
        cur.execute('SELECT capstone_id FROM capstone WHERE capstone_title = %s', (title,))
        existing = cur.fetchone()
        if existing:
            print(f"  -- skipping '{title[:40]}...' (already exists)")
            capstone_ids[idx] = existing[0]
            continue

        spec_id = get_or_create_specialization(cur, spec_name)
        program_id = get_or_create_program(cur, program_name)

        cur.execute(
            """
            INSERT INTO capstone
                (specialization_id, program_id, capstone_title,
                 capstone_year, capstone_file, semester, term)
            VALUES (%s, %s, %s, %s, %s, %s, NULL)
            RETURNING capstone_id
            """,
            (spec_id, program_id, title, year,
             manuscript_storage_key(file_path), semester),
        )
        capstone_id = cur.fetchone()[0]
        set_capstone_keywords(cur, capstone_id, keywords)
        capstone_ids[idx] = capstone_id
        created += 1
        print(f"  -> created capstone: {title[:60]}")

    print(f"  -> {created} capstone(s) created, {len(capstones) - created} skipped.")
    return capstone_ids


def seed_capstone_people(cur, capstone_ids):
    print("Seeding capstone authors and advisers...")
    people_templates = list(SAMPLE_CAPSTONE_PEOPLE.values())
    linked = 0
    for idx, capstone_id in capstone_ids.items():
        people = people_templates[idx % len(people_templates)]

        cur.execute('SELECT 1 FROM "capauth" WHERE capstone_id = %s LIMIT 1', (capstone_id,))
        if cur.fetchone():
            continue  # already has authors/adviser linked

        order = 1
        for person in people["authors"]:
            author_id = get_author_id(cur, person["first"], person.get("middle"), person["last"])
            if author_id is None:
                cur.execute(
                    """
                    INSERT INTO "author" (aut_first_name, aut_middle_name, aut_last_name)
                    VALUES (%s, %s, %s)
                    RETURNING author_id
                    """,
                    (person["first"], person.get("middle") or None, person["last"]),
                )
                author_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO "capauth" (capstone_id, author_id, author_order, role)
                VALUES (%s, %s, %s, 'Author')
                """,
                (capstone_id, author_id, order),
            )
            order += 1

        adviser = people["adviser"]
        adviser_id = get_author_id(cur, adviser["first"], adviser.get("middle"), adviser["last"])
        if adviser_id is None:
            cur.execute(
                """
                INSERT INTO "author" (aut_first_name, aut_middle_name, aut_last_name)
                VALUES (%s, %s, %s)
                RETURNING author_id
                """,
                (adviser["first"], adviser.get("middle") or None, adviser["last"]),
            )
            adviser_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO "capauth" (capstone_id, author_id, author_order, role)
            VALUES (%s, %s, %s, 'Adviser')
            """,
            (capstone_id, adviser_id, order),
        )
        linked += 1

    print(f"  -> authors/advisers linked for {linked} capstone(s).")


def seed_requests(cur, capstone_ids):
    print("Seeding sample manuscript requests...")
    created = 0
    for username, capstone_idx, status, reason in SAMPLE_REQUESTS:
        user_id = get_user_id_by_username(cur, username)
        capstone_id = capstone_ids.get(capstone_idx)
        if not user_id or not capstone_id:
            print(f"  !! could not resolve user '{username}' or capstone index {capstone_idx}, skipping")
            continue

        cur.execute(
            'SELECT 1 FROM request WHERE user_id = %s AND capstone_id = %s',
            (user_id, capstone_id),
        )
        if cur.fetchone():
            print(f"  -- skipping request from {username} (already exists)")
            continue

        now = datetime.now(timezone.utc)

        if status == "pending":
            cur.execute(
                """
                INSERT INTO request (user_id, capstone_id, request_status, request_reason, request_date)
                VALUES (%s, %s, 'pending', %s, %s)
                """,
                (user_id, capstone_id, reason, now),
            )
        else:
            # approved/rejected requests are seeded as already-reviewed,
            # reviewed_by = a current Admin account.
            cur.execute('SELECT role_id FROM role WHERE LOWER(role_name) = %s', (ROLE_ADMIN.lower(),))
            reviewer_role_id = cur.fetchone()
            reviewer_id = None
            if reviewer_role_id:
                cur.execute('SELECT user_id FROM "user" WHERE role_id = %s LIMIT 1', (reviewer_role_id[0],))
                reviewer_row = cur.fetchone()
                reviewer_id = reviewer_row[0] if reviewer_row else None

            cur.execute(
                """
                INSERT INTO request
                    (user_id, capstone_id, request_status, request_reason,
                     request_date, decision_date, reviewed_by, status_reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id, capstone_id, status, reason, now, now, reviewer_id,
                    "Approved for academic research purposes." if status == "approved"
                    else "Did not meet manuscript access criteria.",
                ),
            )
        record_capstone_request(cur, capstone_id, user_id)
        cur.execute('INSERT INTO capstone_view_history (user_id, capstone_id, viewed_at) VALUES (%s, %s, %s) ON CONFLICT (user_id, capstone_id) DO NOTHING',
                    (user_id, capstone_id, now))
        created += 1

    print(f"  -> {created} request(s) created, {len(SAMPLE_REQUESTS) - created} skipped.")


# ──────────────────────────────────────────────────────────────────
# Truncate (used by both --reseed and standalone --truncate)
# ──────────────────────────────────────────────────────────────────

TRUNCATE_TABLES_IN_ORDER = [
    # children first, respecting FKs
    "signup_email_verifications",
    "auth_rate_limit",
    "capstone_view_history",
    "capstone_requests",
    "audit",
    "request",
    '"capauth"',
    '"author"',
    "capstone_keyword",
    "capstone",
    "keyword",
    "password_reset",
    "contact",
    "signup",
    '"logout"',
    "login",
    "slug",
    "ror",
    "kappa",
    '"user"',
    "specialization",
    "program",
    "role",
]


def truncate_tables(cur):
    print("Truncating ALL application data (TRUNCATE ... CASCADE)...")
    table_list = ", ".join(TRUNCATE_TABLES_IN_ORDER)
    cur.execute(f"TRUNCATE {table_list} RESTART IDENTITY CASCADE")
    print("  -> done.")


def run_truncate_only():
    """Standalone --truncate: wipe every seeded table and exit, no reseeding."""
    conn = db_connect()
    conn.autocommit = False
    cur = conn.cursor()
    try:
        truncate_tables(cur)
        conn.commit()
        print("\nTruncate complete.")
    except Exception as exc:
        conn.rollback()
        print(f"\nTruncate FAILED, rolled back. Error: {exc}", file=sys.stderr)
        raise
    finally:
        cur.close()
        conn.close()


# ──────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Seed the Capstone Repository database.")
    parser.add_argument(
        "--reseed", action="store_true",
        help="Delete ALL application data, then reseed fresh data.",
    )
    parser.add_argument(
        "--truncate", action="store_true",
        help="Delete ALL application data and exit. No seeding is performed.",
    )
    parser.add_argument("--users-only", action="store_true", help="Only seed lookups + users.")
    parser.add_argument("--capstones-only", action="store_true", help="Only seed capstones (requires users to already exist).")
    parser.add_argument(
        "--count",
        type=int,
        default=DEFAULT_CAPSTONE_COUNT,
        help=f"Number of capstone records to seed (default: {DEFAULT_CAPSTONE_COUNT}).",
    )
    args = parser.parse_args()
    if args.count < 1:
        parser.error("--count must be at least 1")
    if args.truncate and (args.reseed or args.users_only or args.capstones_only):
        parser.error("--truncate cannot be combined with --reseed, --users-only, or --capstones-only")
    if args.users_only and args.capstones_only:
        parser.error("--users-only cannot be combined with --capstones-only")

    prepare_upload_folders()

    if args.truncate:
        run_truncate_only()
        return

    conn = db_connect()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        if args.reseed:
            truncate_tables(cur)

        seed_lookups(cur)

        if args.capstones_only:
            capstone_ids = seed_capstones(cur, args.count)
            seed_capstone_people(cur, capstone_ids)
            seed_requests(cur, capstone_ids)
        elif args.users_only:
            seed_users(cur)
        else:
            seed_users(cur)
            capstone_ids = seed_capstones(cur, args.count)
            seed_capstone_people(cur, capstone_ids)
            seed_requests(cur, capstone_ids)

        conn.commit()
        print("\nSeeding complete.")

    except Exception as exc:
        conn.rollback()
        print(f"\nSeeding FAILED, rolled back. Error: {exc}", file=sys.stderr)
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
