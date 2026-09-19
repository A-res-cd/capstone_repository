# Project structure

```text
app/
  routes/
    admin/          Repository, users, reports, and other admin features
    authentication/ Sessions, registration, and password recovery
    pages/          Archive browsing, profile, manuscripts, and topics
    main.py         Home, navigation, and shared template context
    forms.py        WTForms validation
    decorators.py   Login and role checks
  db/           PostgreSQL queries
  services/     Application services
  utils/        Uploads, extraction, email, and request helpers
  constants/    Shared constants
  templates/    Jinja templates
  static/       CSS, JavaScript, and images
tests/          Pytest suites, test dependencies, and load/monitoring scripts
scripts/        Desktop test runner and development utilities
database/       Fresh-install SQL schema and local SQL editor sessions
migrations/     Incremental SQL migrations
docs/           Project documentation and timeline
instance/       Local runtime data (ignored by Git)
backups/        Local database backups
```

Run commands from the repository root:

```powershell
python -m pytest
python scripts/test_gui.py
python scripts/extract.py
```

Windows users can double-click `run_tests.bat`. The GUI discovers `tests/test_*.py`.
See [test instructions](../tests/README.md) for dependencies and browser setup.
The extraction example expects its existing manuscript under
`instance/uploads/manuscripts/`.

`database/capreDB.sql` is the fresh-install schema; use the existing migration
instructions for an existing database. `run.py`, `config.py`, `.env`, and the
application's runtime paths remain at their existing locations.

## Finding a route while debugging

| URL or feature | Route module under `app/routes/` |
| --- | --- |
| `/repository`, creation, updates, PDF extraction | `admin/repository.py` |
| Repository manuscript preview/download | `admin/manuscripts.py` |
| `/manage_users`, verification, promotions | `admin/users.py` |
| `/analytics` dashboard | `admin/analytics.py` |
| Analytics reports and workbook exports | `admin/reports.py` |
| `/requests` and review decisions | `admin/requests.py` |
| `/recyclebin`, archive/delete/restore | `admin/archive.py` |
| `/audit-logs`, `/dev-debug` | `admin/audit.py`, `admin/diagnostics.py` |
| `/archive` and saved capstones | `pages/archive.py` |
| `/user-info` and account settings | `pages/profile.py` |
| Manuscript requests, files, citations | `pages/manuscripts.py` |
| `/propose-topic`, `/api/topic-similarity` | `pages/topics.py` |
| `/signin`, `/logout` | `authentication/sessions.py` |
| `/signup`, COR extraction | `authentication/registration.py` |
| Password reset and OTP | `authentication/passwords.py` |

Each package creates one blueprint in `__init__.py`, then imports its feature
modules to register routes. Keep that shared blueprint when adding handlers:
existing `url_for("admin.…")`, `url_for("pages.…")`, and `url_for("auth.…")`
endpoint names stay stable. Loggers use the feature module name, so tracebacks
and logs point to the relevant file.

Import DB helpers from their owning `app.db` module. Keep feature-specific
helpers beside their routes; shared authorization remains in `decorators.py`.
Tests should patch the feature module where a dependency is used, for example
`app.routes.admin.users.get_verification_details`.

`tests/test_route_contract.py` protects the existing URL/endpoint/method map and
anonymous access restrictions. When intentionally adding or changing a public
route, update `tests/fixtures/route_contract.json` to match.
