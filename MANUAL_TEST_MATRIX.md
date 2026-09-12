# CAPRE manual test matrix

Use this checklist after the database and upload services are configured.

## Start-up

1. Create a PostgreSQL database and set `SECRET_KEY`, `PG_HOST`, `PG_PORT`,
   `PG_USER`, `PG_PASSWORD`, and `PG_DB` in `.env`.
   For plain `127.0.0.1` HTTP testing only, set
   `SESSION_COOKIE_SECURE=false`. Use `true` when the app runs behind HTTPS.
2. Run `python migrate.py status`, then `python migrate.py upgrade`.
3. Install Tesseract for scanned COR extraction. Set `TESSERACT_CMD`.
4. Install ClamAV, update its signatures with `freshclam`, then set:

   ```text
   UPLOAD_ANTIVIRUS_COMMAND=C:/Program Files/ClamAV/clamscan.exe
   UPLOAD_ANTIVIRUS_REQUIRED=true
   UPLOAD_RETENTION_CLEANUP_ENABLED=true
   ```

5. Configure SMTP if testing verification, approval, rejection, or OTP email.
6. Start the app with `python run.py` and open `http://127.0.0.1:5000`.
7. Run `python scripts/preflight.py`. It must pass before deployment.

## Student account

Open **Sign up** and upload a COR. Check OCR autofill, editable name fields,
student number, verification email, OTP, and the pending account state.

Open **Profile Overview** (`/profile`) to test:

- profile image upload, preview, and avatar viewer;
- **Register as Capstoner** with a third- or fourth-year COR;
- pending/approved/rejected registration status and professor feedback;
- linked **My Works**, activity totals, recent activity, and notifications.

Open **Explore Archive** (`/archive`) to test search, manuscript request,
approved manuscript view, citation formats, and citation download. Open
**My Requests** (`/my-requests`) to review request status.

Open **Title Similarity** (`/propose-topic`) to test title-only TF-IDF matches.

## Capstone Professor account

Open **Capstoner Review** (`/capstoners`) to reject or approve a registration,
then link the exact author credit. Confirm same-name users remain separate.

Open **Advisory Students** (`/faculty/advisory-students`) to create groups,
rename them, select up to four verified students, collapse/expand groups, and
remove a student without changing authorship or account status.

Open **Capstone Repository** (`/repository`) to create or manage repository
records when the account has the required permission.

## Admin account

Open **User Management** (`/manage_users`) to review a private COR in the
verification modal, inspect the native PDF viewer, approve, or reject it.

Open **Audit Logs** (`/audit-logs`) to filter summarized administrative
activity. Open **Analytics** (`/analytics`) to check summarized repository
reports and exports. Use **Capstone Repository** (`/repository`) for admin
record management.

## Activity notification test

Use two student accounts. Link Student A to a capstone author credit. Sign in
as Student B and perform a manuscript request, approved manuscript view, and
citation. Return to Student A's Profile Overview and verify the totals and bell
messages. The requester identity must not appear. Repeat the same event within
the deduplication window and confirm the count does not increase.

## Operations checks

```text
GET /health/live
GET /health/ready
python scripts/report_orphaned_uploads.py
python scripts/backup_database.py --output backups/capre_predeploy.dump
python scripts/verify_backup.py --input backups/capre_predeploy.dump
```

Only restore into a disposable database first:

```text
python scripts/restore_database.py --input backups/capre_predeploy.dump --confirm
```

Automated local checks:

```text
python -m pytest -q
```

The two legacy E2E checks skip unless a separate server is running at
`localhost:5000`.
