# CAPRE Testing Setup

## Desktop test runner

From the repository root, double-click `run_tests.bat` on Windows or run:

```powershell
python scripts/test_gui.py
```

The GUI discovers this branch's `tests/test_*.py` files and defaults to the
local `venv` or `.venv` interpreter. Run all tests or selected files, filter with
pytest's `-k` syntax, inspect live output and per-test tracebacks, rerun failures,
and save a text report. No tests run automatically when the window opens.

The light/dark toggle uses this branch's website CSS colors. Enable “Show browser
windows” for headed Playwright tests or “Stream test prints” for uncaptured output.
“Stop after current test” allows fixture cleanup; “Force stop” kills the owned
test process tree and can interrupt cleanup.

Install dependencies into the interpreter selected in the GUI, from the repository root:

```powershell
python -m pip install -r tests/requirements.txt
python -m playwright install
```

Tkinter is included in standard Windows Python installations. Database tests
still require PostgreSQL tools and browser tests need their existing fixtures or
running application. Missing dependencies and test errors appear in the GUI.
Locust and SQL monitoring scripts use their own tools, not pytest.

## Install
```
pip install -r tests/requirements.txt
playwright install
```

## 1. Load testing (Locust)
```
locust -f tests/locustfile.py --host=http://localhost:5000
```
Open http://localhost:8089 → set number of users + spawn rate → start.
Edit selectors/payloads in `locustfile.py` to match your actual `auth`,
`main`, `admin` blueprint routes and form field names.

## 2. E2E browser testing (Playwright)
```
python -m pytest tests/test_e2e_workflow.py --headed
```
Update CSS selectors in `test_e2e_workflow.py` to match your Jinja
templates (login form, archive result cards, error messages).

## 3. Database monitoring
While Locust runs, open `postgres_monitoring.sql` in psql/pgAdmin and
run each query to check active connections, slow queries, and cache
hit ratio.

## 4. Multi-device / multi-network testing
Expose your local Flask server via VS Code Dev Tunnel, then hit that
URL from real phones/laptops on Wi-Fi and mobile data to verify IP
logging and responsiveness.

## 5. API testing
Import your `/signin`, `/signup`, `/request`, `/archive` routes into
Postman or Bruno for endpoint-level correctness checks (separate from
Locust's load testing).
