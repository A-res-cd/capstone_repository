def get_nav_links(role):
    links = [
        {"name": "Home", "url": "/", "icon": "bx bx-home", "roles": ["Admin", "User"]},
        {"name": "Capstone Projects", "url": "/projects", "icon": "bx bx-folder", "roles": ["Admin", "User"]},
        {"name": "Requests", "url": "/requests", "icon": "bx bx-file", "roles": ["Admin"]},
        {"name": "User Settings", "url": "/settings", "icon": "bx bx-user", "roles": ["Admin", "User"]},
        {"name": "Similarity Analysis", "url": "/analysis", "icon": "bx bx-bar-chart", "roles": ["Admin"]},
    ]

    # filter by role
    return [link for link in links if role in link["roles"]]