from .main     import main
from .authentication     import auth
from .admin    import admin
from .pages import pages
from .faculty import faculty
from .system import system

blueprints = [main, auth, admin, pages, faculty, system]
