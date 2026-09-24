"""Stable application names for database roles."""

ROLE_STUDENT = "Student"
ROLE_FACULTY = "Faculty"
ROLE_ADMIN = "System Administrator"
ROLE_RET_CHAIR = "RET Chair"
ROLE_CAPSTONE_PROFESSOR = "Capstone Professor"

ALL_ROLES = (
    ROLE_STUDENT,
    ROLE_FACULTY,
    ROLE_ADMIN,
    ROLE_RET_CHAIR,
    ROLE_CAPSTONE_PROFESSOR,
)

# Compatibility only for tests or old request contexts that contain role_id
# but were created before role_name was loaded into g.user.
LEGACY_ROLE_NAMES_BY_ID = {
    1: ROLE_STUDENT,
    2: ROLE_FACULTY,
    3: ROLE_RET_CHAIR,
    4: ROLE_CAPSTONE_PROFESSOR,
}

ACADEMIC_ROLES = (ROLE_STUDENT, ROLE_FACULTY, ROLE_RET_CHAIR, ROLE_CAPSTONE_PROFESSOR)
PRIVILEGED_ROLES = (ROLE_ADMIN, ROLE_RET_CHAIR)


def landing_endpoint(role):
    return {
        ROLE_ADMIN: "system.overview",
        ROLE_RET_CHAIR: "admin.overview",
        ROLE_CAPSTONE_PROFESSOR: "admin.view_capstone_repository",
    }.get(role, "pages.browse")
