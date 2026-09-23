"""Mobile-width browser smoke test; API responses are deterministic fixtures."""
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
from urllib.request import urlopen

from playwright.sync_api import expect
import pytest


@pytest.fixture(scope="module")
def mobile_url():
    root = Path(__file__).resolve().parents[1] / "mobile"
    vite = root / "node_modules/vite/bin/vite.js"
    if not vite.exists() or not shutil.which("node"):
        pytest.skip("Run npm ci in mobile/ before mobile UI tests")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen(
            [shutil.which("node"), str(vite), "--host", "127.0.0.1", "--port", str(port), "--strictPort"],
            cwd=root, stdout=output, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            for _ in range(100):
                try:
                    with urlopen(url, timeout=1):
                        break
                except OSError:
                    if process.poll() is not None:
                        output.seek(0)
                        pytest.fail(output.read().decode(errors="replace"))
                    time.sleep(.1)
            else:
                pytest.fail("Vite did not start")
            yield url
        finally:
            process.terminate()
            process.wait(timeout=10)


def blank_pdf():
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 400] /Resources << >> /Contents 4 0 R >>",
        b"<< /Length 0 >>\nstream\n\nendstream",
    ]
    data = b"%PDF-1.4\n"
    offsets = [0]
    for index, value in enumerate(objects, 1):
        offsets.append(len(data))
        data += f"{index} 0 obj\n".encode() + value + b"\nendobj\n"
    xref = len(data)
    data += b"xref\n0 5\n0000000000 65535 f \n"
    for offset in offsets[1:]:
        data += f"{offset:010d} 00000 n \n".encode()
    return data + f"trailer\n<< /Root 1 0 R /Size 5 >>\nstartxref\n{xref}\n%%EOF".encode()


def test_mobile_login_search_pdf_notifications_and_logout(page, mobile_url):
    calls = []
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.set_viewport_size({"width": 390, "height": 844})
    item = {"capstone_id": 1, "capstone_title": "Campus Research", "capstone_year": 2026, "program_name": "IT"}

    def respond(route):
        path = route.request.url.split("/api/v1", 1)[1]
        calls.append(path)
        if path == "/auth/login":
            data = {"access_token": "access", "refresh_token": "refresh"}
        elif path == "/auth/logout":
            route.fulfill(status=204)
            return
        else:
            assert route.request.headers.get("authorization") == "Bearer access"
            if path.startswith("/capstones?"):
                data = {"items": [item], "total": 1, "page": 1, "page_size": 12}
            elif path == "/capstones/1":
                data = {"item": item, "can_view": True}
            elif path == "/capstones/1/file":
                route.fulfill(content_type="application/pdf", body=blank_pdf())
                return
            elif path == "/notifications":
                data = {"items": [{"notification_title": "Request approved", "request_status": "approved"}], "unread_count": 1}
            elif path == "/notifications/read":
                route.fulfill(status=204)
                return
            elif path == "/me":
                data = {"user": {"user_first_name": "Maria", "user_last_name": "Cruz", "role_name": "Student"}}
            else:
                pytest.fail(f"Unexpected mobile request: {path}")
        route.fulfill(content_type="application/json", body=json.dumps(data))

    page.route("**/api/v1/**", respond)
    page.goto(mobile_url)
    page.get_by_label("Username", exact=True).fill("maria")
    page.get_by_label("Password", exact=True).fill("secret")
    page.get_by_role("button", name="Sign in", exact=True).click()
    expect(page.get_by_role("heading", name="Explore the repository")).to_be_visible()
    page.get_by_role("searchbox").fill("Campus")
    page.get_by_role("button", name="Search", exact=True).click()
    expect(page).to_have_url(f"{mobile_url}/#repository?search=Campus")
    page.get_by_role("link", name="Campus Research").click()
    page.get_by_role("button", name="Read manuscript").click()
    expect(page.get_by_text("Page 1 of 1", exact=True)).to_be_visible(timeout=15000)
    expect(page.locator("canvas")).to_be_visible()
    page.get_by_role("link", name="Notifications", exact=True).click()
    expect(page.get_by_role("heading", name="Request approved")).to_be_visible()
    page.get_by_role("button", name="Mark all read").click()
    expect(page.get_by_role("heading", name="Request approved")).to_be_visible()
    page.get_by_role("link", name="Profile", exact=True).click()
    expect(page.get_by_role("heading", name="Maria Cruz")).to_be_visible()
    assert page.evaluate("localStorage.length") == 0
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.get_by_role("button", name="Sign out").click()
    expect(page.get_by_role("button", name="Sign in", exact=True)).to_be_visible()
    assert "/auth/logout" in calls and "/notifications/read" in calls
    assert not errors


def test_mobile_offline_shell_and_retry(page, mobile_url):
    page.goto(mobile_url)
    expect(page.get_by_role("button", name="Sign in", exact=True)).to_be_visible()
    page.context.set_offline(True)
    expect(page.get_by_text("You are offline. Connect to load your repository.")).to_be_visible()
    page.get_by_label("Username", exact=True).fill("maria")
    page.get_by_label("Password", exact=True).fill("secret")
    page.get_by_role("button", name="Sign in", exact=True).click()
    expect(page.locator("#message")).to_be_visible()
    expect(page.get_by_role("button", name="Sign in", exact=True)).to_be_enabled()
    page.context.set_offline(False)
