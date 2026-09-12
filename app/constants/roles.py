"""Stable application names for database roles."""

ROLE_STUDENT = "Student"
ROLE_FACULTY = "Faculty"
ROLE_ADMIN = "Admin"
ROLE_CAPSTONE_PROFESSOR = "Capstone Professor"

ALL_ROLES = (
    ROLE_STUDENT,
    ROLE_FACULTY,
    ROLE_ADMIN,
    ROLE_CAPSTONE_PROFESSOR,
)

# Compatibility only for tests or old request contexts that contain role_id
# but were created before role_name was loaded into g.user.
LEGACY_ROLE_NAMES_BY_ID = {
    1: ROLE_STUDENT,
    2: ROLE_FACULTY,
    3: ROLE_ADMIN,
    4: ROLE_CAPSTONE_PROFESSOR,
}
