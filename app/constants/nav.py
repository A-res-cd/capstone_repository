def get_nav_links(role):
    links = [
        # --- Process 6.0: Generate System Analytics and Report — Admin only ---
        # Sub-processes: View Audit Logs (6.1), Generate Informational Reports (6.2),
        # View Informational Reports (6.3), Generate Informational Analytics (6.5)
        {
            "name": "Analytics & Reports",
            "title": "Analytics & Reports",
            "url": "admin.analytics",
            "icon": "bx bx-bar-chart-alt-2",
            "roles": ["Admin"],
            "section": "Management"
        },

        # --- Process 2.0: Manage User and Role — Admin only ---
        {
            "name": "Users & Roles",
            "title": "User Management",
            "url": "admin.manage_users",
            "icon": "bx bx-group",
            "roles": ["Admin"],
            "section": "Management"
        },

        # --- Process 3.0: Manage Capstone Repository — Admin + Capstone Professor ---
        {
            "name": "Capstone Repository",
            "title": "Manage Repository",
            "url": "admin.view_capstone_repository",
            "icon": "bx bx-folder-open",
            "roles": ["Admin", "Capstone Professor", "Faculty"],
            "section": "Capstone"
        },

        {
            "name": "Recycle Bin",
            "title": "Recycle Bin",
            "url": "admin.view_archived_capstones",
            "icon": "bx bx-trash",
            "roles": ["Admin"],
            "section": "Management"
        },

        # --- Process 4.0: Explore Capstone Archive — All roles ---
        {
            "name": "Explore Archive",
            "title": "Explore Capstone Archive",
            "url": "pages.browse",
            "icon": "bx bx-search-alt",
            "roles": ["Admin", "Capstone Professor", "Faculty", "Student"],
            "section": "Capstone"
        },

        # --- Sub-process 4.5 (Level3ViewCapstoneData): Manuscript access requests — Student only ---
        # Capstone-agnostic — lists every request the student has made,
        # across all capstones. (The per-capstone request form lives at
        # pages.request_capstone, which needs a capstone_id and can't be
        # a standalone nav target — both routes render the same merged
        # template, app/templates/global/all_requests.html.)
        {
            "name": "My Requests",
            "title": "My Requests",
            "url": "pages.all_requests",
            "icon": "bx bx-file-blank",
            "roles": ["Student"],
            "section": "Capstone"
        },

        # --- Sub-process 4.5 (Level3ViewCapstoneData): Request approval — Admin only ---
        # Students submit access requests; Admin reviews and decides.
        # Shown as an Admin nav item for managing incoming requests.
        {
            "name": "Requests",
            "title": "Requests",
            "url": "admin.view_requests",
            "icon": "bx bx-file-blank",
            "roles": ["Admin"],
            "section": "Management"
        },

        {
            "name": "Capstoner Review",
            "title": "Capstoner Review",
            "url": "admin.capstoner_review",
            "icon": "bx bx-user-check",
            "roles": ["Capstone Professor"],
            "section": "Management"
        },

        {
            "name": "Advisory Students",
            "title": "Advisory Students",
            "url": "faculty.manage_capstone_users",
            "icon": "bx bx-group",
            "roles": ["Capstone Professor"],
            "section": "Management"
        },

        # --- Data mining: content-based topic-similarity check — Student only ---
        # Not tied to an existing DFD process number yet (new feature).
        # Lets a student check a proposed title against archived titles
        # before submitting, via TF-IDF + cosine similarity.
        {
            "name": "Title Similarity",
            "title": "Title Similarity",
            "url": "pages.propose_topic",
            "icon": "bx bx-bulb",
            "roles": ["Student"],
            "section": "Capstone"
        },

        # --- Process 5.0: Manage User Information — All roles ---
        # Level2ManageUserInformation.drawio shows all 4 actors
        # (Admin, Capstone Professor, Student, Faculty) with flows
        # to 'view information' and 'update information'.
        {
            "name": "Profile Overview",
            "title": "Profile Overview",
            "url": "pages.profile_overview",
            "icon": "bx bx-user",
            "roles": ["Admin", "Capstone Professor", "Faculty", "Student"],
            "section": "Account"
        },

        # --- Not a real DFD process — an internal dev tool that mostly
        # trolls, occasionally shows something actually useful. Admin
        # only; see admin.dev_debug for the odds. ---
        # {
        #     "name": "Developer Debug Tool",
        #     "title": "Developer Debug Tool",
        #     "url": "admin.dev_debug",
        #     "icon": "bx bx-terminal",
        #     "roles": ["Admin"],
        #     "section": "Account"
        # },
    ]

    # Filter links by role
    filtered = [link for link in links if role in link["roles"]]

    # Group links by section, preserving insertion order
    sections = {}
    for link in filtered:
        sec = link["section"]
        if sec not in sections:
            sections[sec] = []
        sections[sec].append(link)

    return filtered, sections


# ─────────────────────────────────────────────────────────────────────────────
# Branch-page breadcrumb mapping
#
# Keys are URL *prefixes* (checked with startswith) for pages that don't have
# their own nav link. Each entry defines:
#   ancestors  — an ordered list of (endpoint, label) tuples, root-first,
#                for every level between the root nav link and this page.
#                Most branch pages sit one level below a root nav link, so
#                this list usually has one item — but it can hold as many
#                ancestor levels as the page is actually nested under,
#                which is what lets the header render a full
#                "root -> child -> child" chain instead of just root -> current.
#   page_name  — this page's own label, shown last and not a link.
# ─────────────────────────────────────────────────────────────────────────────
_BRANCH_MAP = [
    ("/faculty/advisory-students/", [("faculty.manage_capstone_users", "Advisory Students")], "Update roster"),
    # Capstone detail / PDF viewer  →  parent is whichever list page makes sense
    ("/abstract/",          [("pages.browse",                   "Explore Archive")], "View Abstract"),
    ("/manuscript/view/",   [("pages.all_requests",              "My Requests")],     "View Manuscript"),
    # Per-capstone request form  →  nested under Explore Archive -> My Requests,
    # since a student reaches this form by browsing the archive first.
    ("/requests/",          [("pages.browse",                   "Explore Archive"),
                              ("pages.all_requests",              "My Requests")],     "Request Manuscript"),
    # Admin: view/edit individual capstone  →  parent is Repository
    ("/repository/view/",   [("admin.view_capstone_repository", "Capstone Repository")], "View Capstone"),
    ("/repository/update/", [("admin.view_capstone_repository", "Capstone Repository")], "Edit Capstone"),
    # Admin: decide on a request  →  parent is Requests
    ("/repository/decide/", [("admin.view_requests",            "Requests")],         "Review Request"),
]


def get_breadcrumb(nav_links, path):
    """
    Returns an ordered list of crumbs, root-first:
      [ {"name": ..., "url": ...}, {"name": ..., "url": ...}, ... ]

    Every crumb except the last has a resolved "url" and renders as a link;
    the last crumb represents the current page, has "url": None, and renders
    as plain (non-link) text. The header template just loops over this list
    and joins the crumbs with a separator — so it naturally renders
    "root -> child -> child -> ... -> current" for any depth, rather than
    being limited to a single parent/current pair.

    For a direct nav-link page (e.g. /archive), this is a single crumb:
      [ {"name": "Explore Archive", "url": None} ]

    For a branch page nested under N ancestors (e.g. /requests/5), this is
    N + 1 crumbs, e.g.:
      [ {"name": "Explore Archive", "url": "/archive"},
        {"name": "My Requests",     "url": "/my-requests"},
        {"name": "Request Manuscript", "url": None} ]
    """
    def _resolve_url(endpoint):
        parent_url = next(
            (l["url"] for l in nav_links if l.get("_endpoint") == endpoint),
            None
        )
        if parent_url:
            return parent_url
        try:
            from flask import url_for
            return url_for(endpoint)
        except Exception:
            return "#"

    # Check if this is a direct nav-link page first
    for link in nav_links:
        if link["url"] == path:
            return [{"name": link.get("title") or link["name"], "url": None, "endpoint": None}]

    # Check branch map
    for prefix, ancestors, page_name in _BRANCH_MAP:
        if path.startswith(prefix):
            crumbs = [
                {"name": label, "url": _resolve_url(endpoint), "endpoint": endpoint}
                for endpoint, label in ancestors
            ]
            crumbs.append({"name": page_name, "url": None, "endpoint": None})
            return crumbs

    # Unknown page — no breadcrumb
    return []


def get_role_meta(role):
    """
    Returns display metadata for a given role.
    Used to render the role badge in the navbar.
    """
    meta = {
        "Admin": {
            "label": "Administrator",
            "badge_class": "badge-admin",
            "icon": "bx bx-crown",
        },
        "Capstone Professor": {
            "label": "Capstone Professor",
            "badge_class": "badge-professor",
            "icon": "bx bx-book-reader",
        },
        "Faculty": {
            "label": "Faculty",
            "badge_class": "badge-faculty",
            "icon": "bx bx-chalkboard",
        },
        "Student": {
            "label": "Student",
            "badge_class": "badge-student",
            "icon": "bx bx-user",
        },
    }
    return meta.get(role, {"label": role, "badge_class": "", "icon": "bx bx-user"})

def resolve_title(nav_sections, nav_links, path):
    for link in nav_links:
        if link["url"] == path:
            return link.get("title") or link["name"]
    return None
