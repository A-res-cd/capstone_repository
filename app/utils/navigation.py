from urllib.parse import urlsplit

from flask import request, session


LAST_PAGE_SESSION_KEY = "last_successful_page"


def last_page_url(fallback="/", avoid_current=False):
    """Return the last successful internal page stored in the session."""
    candidate = session.get(LAST_PAGE_SESSION_KEY)
    if not isinstance(candidate, str) or len(candidate) > 1024:
        return fallback

    parsed = urlsplit(candidate)
    if (
        parsed.scheme or parsed.netloc or "\\" in parsed.path
        or not parsed.path.startswith("/") or parsed.path.startswith("//")
    ):
        return fallback
    if avoid_current and parsed.path == request.path:
        return fallback
    return candidate
