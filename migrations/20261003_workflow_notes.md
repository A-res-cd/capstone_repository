Apply with `python scripts/migrate.py upgrade` after a verified backup.

- `python scripts/backup_database.py --output <private-directory> --include-uploads`
  creates a PostgreSQL custom-format dump and separate upload ZIP. Keep these
  outside Git/public folders, restrict access, and encrypt storage according to
  university policy. Configure a scheduled job only after the university chooses
  the backup schedule and retention period.
- Test a restore using `createdb <new-test-database>` followed by
  `pg_restore --no-owner --no-privileges --exit-on-error --dbname <new-test-database> <dump>`.
  Restore uploaded files into an isolated upload directory as well. Never use
  the production database name for a restore test.
- Run `python scripts/backfill_abstracts.py` after migration. Missing/non-PDF
  files retain title/keyword matching. New and edited PDFs cache their abstracts.
- Old publication statuses stay NULL (Not reviewed). New capstones default to
  unpublished; an editor confirms publication with the checkbox. Publication
  does not grant access to restricted manuscripts.
- BSDS uses `No specialization`. BSIT mappings are Database Systems Technology,
  Network Systems Technology, and Web Systems Technology. Existing identifiers
  are preserved, with separate program/specialization codes. The follow-up
  migration removes the mapping table; browser filtering and server validation
  share `app/constants/programs.py`. The applied original migration stays unchanged.
- Email remains the recovery and account-notice channel. Phone preference is
  for contact; SMS delivery and phone-only registration are not enabled.
- Terms acceptance records notice version 2026-10-03 and timestamp for new
  registrations. Historic users are not falsely marked as having accepted it.
- University follow-up: supply the official privacy contact and retention
  periods for accounts, CORs, review/audit records, and backups. The notice
  points to official university privacy channels until these are supplied;
  it does not claim a specific retention schedule or full legal compliance.
- These are additive migrations. Before rolling back schema, roll back the
  application code; retain new columns/data or restore into a separate database
  and verify it before switching connections.
