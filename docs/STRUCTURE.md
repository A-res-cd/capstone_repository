# Project structure

The application uses Flask blueprints with feature modules inside the larger
blueprints. Blueprint names, endpoints, URL paths, and template locations remain
stable when a feature moves between Python files.

```text
app/
  routes/
    admin/          # Analytics, audit, users, requests, capstoners, repository, archive
    pages/          # Archive browsing, profile, manuscripts, topic proposals
    authentication.py
    faculty.py
    main.py
    forms.py
    decorators.py
  services/         # Application workflows and domain calculations
  db/               # PostgreSQL queries, grouped by domain
  utils/            # Uploads, extraction, email rendering, request helpers
  constants/
  templates/        # Jinja templates grouped by role or shared use
  static/           # CSS, JavaScript, images
tests/              # Regression, database, browser, and load tests
scripts/            # Migration, backup, restore, and development commands
database/           # Fresh-install SQL schema
migrations/         # Ordered incremental SQL migrations
docs/               # Test matrix, production readiness, project documents
instance/           # Local runtime data; ignored by Git
```

Routes handle HTTP input, authorization, responses, and template rendering.
Put multi-step application workflows in `services/`, and SQL in `db/`.
Simple reads can call their domain DB helper directly without a pass-through
service. Import the owning DB module rather than the legacy `db/database.py`
compatibility exports when adding or moving code.

Each route package creates its blueprint in `__init__.py`, then imports its feature
modules to register routes. Use the shared blueprint in those modules so existing
`url_for("admin.…")` and `url_for("pages.…")` calls keep working. Tests should patch
dependencies in the feature module that actually uses them.

Run commands from the repository root:

```powershell
python -m pytest -q
python scripts/migrate.py status
python scripts/migrate.py upgrade
```

Install test dependencies with `pip install -r tests/requirements.txt`.
Database integration tests require PostgreSQL's `initdb` and `pg_ctl` on PATH.
Browser tests require Playwright browsers; see [test instructions](../tests/README.md).
The sample COR tests require the existing local PDF under `app/static/uploads/registration/`.

`database/capreDB.sql` is for a fresh database. Use incremental migrations for
existing data. Local seeder and SQL editor session files remain ignored by Git.
