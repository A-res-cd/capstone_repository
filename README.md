# 1. Clone the repo
git clone https://github.com/AresFrappe/capstone_repository.git
cd repository

# 2. Create virtual environment
# Windows
python -m venv venv

# 3. Activate virtual environment (run in terminal)
# Windows (CMD)
venv\Scripts\activate
# Windows (PowerShell)
venv\Scripts\Activate.ps1

# 4. Install dependencies
pip install -r requirements.txt

# 5. Create .env file
inside .env file put:
SECRET_KEY = your-secret-key

PG_HOST = localhost
PG_PORT = 5432
PG_USER = your-postgres-user
PG_PASSWORD = your-postgres-password
PG_DB = your-database-name

MAIL_SERVER = smtp.example.com
MAIL_PORT = 587
MAIL_USERNAME = your-email@example.com
MAIL_PASSWORD = your-email-password

UPLOAD_MANUSCRIPT_FOLDER = app/static/uploads/manuscripts
UPLOAD_REGISTRATION_FOLDER = app/static/uploads/registration
UPLOAD_AVATAR_FOLDER = app/uploads/avatars
UPLOAD_MANUSCRIPT_MAX_BYTES = 20971520
UPLOAD_AVATAR_MAX_BYTES = 5242880
UPLOAD_ORPHAN_RETENTION_DAYS = 30

# Required for automatic OCR of scanned COR files.
# Install the Windows engine separately from:
# https://github.com/UB-Mannheim/tesseract/wiki
TESSERACT_CMD = C:\Program Files\Tesseract-OCR\tesseract.exe

# 6. Run the app
flask run
or
python run.py

# 7. Run the tests
pytest app/test/test_cor_extractor.py app/test/test_cor_pdf.py -q

# 8. When done, deactivate environment
deactivate

## COR upload and automatic extraction

Signup accepts a Certificate of Registration as a PDF. The upload appears first
in the form and attempts to extract the registration number, student number,
first name, middle name, and last name. Extracted values remain editable before
account creation. The sample COR test is stored at
`app/static/uploads/registration/Sapin_Aaries_M._3e7f3448731c472d93c9912b893e73ac.pdf`.

The sample COR is image-based, so Tesseract OCR must be installed for automatic
extraction. `pytesseract` in `requirements.txt` is only the Python wrapper. If
Tesseract is unavailable, the form shows a warning and allows manual entry.

Run `migrations/20260911_cor_registration.sql` on an existing database. It
creates the normalized `cor_registration` table used by capstoner eligibility.

Run `migrations/20260911_user_avatars.sql` on an existing database to create the
normalized private `user_avatar` table. Avatar files are stored outside the
static directory and served only to the signed-in owner. The profile overview
and the header fall back to initials when no image is uploaded.

## Database migrations

Use the explicit migration runner after creating the database and before
starting the web process:

```text
python migrate.py status
python migrate.py upgrade
```

Migrations run in filename order, are recorded in `schema_migration`, and are
protected by a PostgreSQL advisory lock. Applied migration checksums cannot be
changed silently. The web app does not modify the database during startup.

## Production database operations

The liveness probe is `GET /health/live`. The readiness probe is
`GET /health/ready`; it returns `503` until PostgreSQL is reachable and every
tracked migration is applied with its original checksum.

Create a password-safe custom-format backup with the PostgreSQL client tools:

```text
python scripts/backup_database.py --output backups/capre_predeploy.dump
```

Restore only into the intended database after checking the backup and target:

```text
python scripts/restore_database.py --input backups/capre_predeploy.dump --confirm
```

Backup files are ignored by Git. Store them in protected backup storage and
test a restore before treating a deployment as production-ready.

Uploaded manuscripts are checked by extension, size, and file signature before
they are stored. Review old unreferenced private files before deleting them:

```text
python scripts/report_orphaned_uploads.py
```

The report is read-only. Do not delete a reported file until its database
references and retention policy have been reviewed.
