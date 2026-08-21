"""
database.py — compatibility shim.

This file used to contain all 57 query functions in one 1,934-line
module. It's been split by domain into:

    connection.py   — db_connect()
    audit.py        — log_audit()
    auth.py         — sign up/in/out, verification, password reset/OTP
    capstones.py    — capstone CRUD, keywords, programs, corpus
    archive.py      — recycle bin + public Explore Archive
    users.py        — Manage Users (accounts, contacts, roles)
    requests.py     — manuscript/full-view access requests
    analytics.py    — Analytics & Reports aggregate queries

Every function keeps its original name and signature — nothing in
app/routes/*.py or app/auth_utils.py needs to change. New code should
import directly from the specific module above instead of this shim
(e.g. `from app.db.capstones import get_all_capstones`), since that's
the whole point of the split — findability. This file only exists so
existing `from app.db.database import X` imports keep working.
"""

from app.db.connection import db_connect
from app.db.audit import log_audit

from app.db.auth import (
    STUDENT_PATTERN, PROFESSOR_PATTERN, ADMIN_PATTERN,
    EMAIL_PATTERN, USERNAME_PATTERN,
    LOCKOUT_THRESHOLD, LOCKOUT_DURATION,
    OTP_EXPIRY_MINUTES, OTP_MAX_ATTEMPTS,
    detect_role, get_verifier_track, screen_account,
    create_verification_request, reapply_for_verification,
    get_device_ip, get_role_id, create_user, sign_in,
    lookup_user_for_reset, create_otp, verify_otp, change_password,
    change_own_password,
    sign_out, get_pending_verifications, review_verification_request,
)

from app.db.capstones import (
    create_capstone_project, insert_keywords, get_programs,
    get_specializations, get_used_keyword, update_keyword,
    get_capstone_details, update_capstone_record, get_all_capstones,
    get_capstone_authors, get_capstone_people, set_capstone_people,
    add_citations, get_capstones_corpus,
)

from app.db.archive import (
    ARCHIVE_RETENTION_DAYS,
    get_archived_capstones, purge_expired_archived_capstones,
    delete_capstone, add_to_bin, restore_capstone,
    get_archive_capstones, get_archive_years,
)

from app.db.users import (
    get_users, get_own_profile, get_user_contacts, upsert_user_contact, get_all_roles,
    update_user_role, delete_user_account, set_account_status, delete_own_account,
    submit_promotion_request, get_pending_promotion_requests, get_own_promotion_requests,
    review_promotion_request, cancel_promotion_request,
)

from app.db.requests import (
    request_fullview, get_all_requests, review_request,
    get_user_requests, cancel_manuscript_request, get_requests_by_status,
)

from app.db.analytics import (
    get_capstones_by_program, get_capstone_program_summary,
    get_capstone_trend_by_specialization, get_capstones_by_specialization,
    get_capstone_status_flags, get_top_cited_capstones,
)
