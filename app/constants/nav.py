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
            "roles": ["Admin", "Capstone Professor"],
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

        # --- Process 5.0: Manage User Information — All roles ---
        # Level2ManageUserInformation.drawio shows all 4 actors
        # (Admin, Capstone Professor, Student, Faculty) with flows
        # to 'view information' and 'update information'.
        {
            "name": "User Information",
            "title": "User Settings",
            "url": "pages.user_info",
            "icon": "bx bx-id-card",
            "roles": ["Admin", "Capstone Professor", "Faculty", "Student"],
            "section": "Account"
        },
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
# their own nav link. Values define:
#   parent_endpoint  — the nav link this branch "belongs to" (for active state)
#   parent_name      — the nav link label shown in the breadcrumb
#   page_name        — the current page label shown after the ">"
# ─────────────────────────────────────────────────────────────────────────────
_BRANCH_MAP = [
    # Capstone detail / PDF viewer  →  parent is whichever list page makes sense
    ("/abstract/",          "pages.browse",                  "Explore Archive",      "View Abstract"),
    ("/manuscript/view/",   "pages.all_requests",            "My Requests",          "View Manuscript"),
    # Per-capstone request form  →  parent is My Requests (student) or Archive
    ("/requests/",          "pages.all_requests",            "My Requests",          "Request Manuscript"),
    # Admin: view/edit individual capstone  →  parent is Repository
    ("/repository/view/",   "admin.view_capstone_repository","Capstone Repository",  "View Capstone"),
    ("/repository/update/", "admin.view_capstone_repository","Capstone Repository",  "Edit Capstone"),
    # Admin: decide on a request  →  parent is Requests
    ("/repository/decide/", "admin.view_requests",           "Requests",             "Review Request"),
]


def get_breadcrumb(nav_links, path):
    """
    Returns a dict:
      { parent_url, parent_name, page_name, parent_endpoint }

    For a direct nav-link page (e.g. /archive):
      parent_url   = None  (no parent — it IS the root)
      page_name    = link title
      parent_name  = None

    For a branch page (e.g. /abstract/5):
      parent_url   = resolved URL of the parent nav link
      parent_name  = nav link label
      page_name    = branch page label
    """
    # Check if this is a direct nav-link page first
    for link in nav_links:
        if link["url"] == path:
            return {
                "parent_url":      None,
                "parent_name":     None,
                "page_name":       link.get("title") or link["name"],
                "parent_endpoint": None,
            }

    # Check branch map
    for prefix, parent_endpoint, parent_name, page_name in _BRANCH_MAP:
        if path.startswith(prefix):
            # Find the resolved URL for the parent endpoint from nav_links
            parent_url = next(
                (l["url"] for l in nav_links if l.get("_endpoint") == parent_endpoint),
                None
            )
            # Fallback: try to build it from flask url_for
            if not parent_url:
                try:
                    from flask import url_for
                    parent_url = url_for(parent_endpoint)
                except Exception:
                    parent_url = "#"
            return {
                "parent_url":      parent_url,
                "parent_name":     parent_name,
                "page_name":       page_name,
                "parent_endpoint": parent_endpoint,
            }

    # Unknown page — no breadcrumb
    return {
        "parent_url":      None,
        "parent_name":     None,
        "page_name":       None,
        "parent_endpoint": None,
    }


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