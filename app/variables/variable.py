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
            "url": "admin.repository",
            "icon": "bx bx-folder-open",
            "roles": ["Admin", "Capstone Professor"],
            "section": "Capstone"
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

        # --- Sub-process 4.5 (Level3ViewCapstoneData): Request approval — Admin only ---
        # Students submit access requests; Admin reviews and decides.
        # Shown as an Admin nav item for managing incoming requests.
        {
            "name": "Requests",
            "title": "Requests",
            "url": "admin.requests",
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
            "url": "global.user_info",
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
    if nav_sections:
        for section in nav_sections.values():
            for link in section:
                if link["url"] == path:
                    return link.get("title") or link["name"]

    elif nav_links:
        for link in nav_links:
            if link["url"] == path:
                return link.get("title") or link["name"]

    return None