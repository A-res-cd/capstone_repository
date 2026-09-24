# System Administrator and RET Chair

The System Administrator maintains the application. The RET Chair holds the
former Admin's academic authority. Existing Faculty, Student, and Capstone
Professor permissions are preserved. Maintenance uses the web console.
Native Android/iOS packaging and its API have been removed. The historical
mobile-session migration remains for migration-history compatibility; the
website does not use that table.

## Deployment and account migration

1. Back up the existing database and private upload directories before upgrading.
2. Run `python scripts/migrate.py upgrade`. The migration renames the old
   `Admin` role to `RET Chair`, preserving its accounts and academic authority.
   It creates `System Administrator` but assigns nobody automatically. If both
   old `Admin` and `RET Chair` roles already exist, reconcile them explicitly
   before rerunning the migration.
3. Choose an existing active account for maintenance access. On the server run:

   ```text
   python scripts/provision_system_admin.py --user-id USER_ID --reason "Approved maintenance operator" --confirm PROVISION
   ```

   This replaces that account's academic role. Keep a separate RET Chair account.
   The command cannot remove the last active account from either privileged role.
   System Administrator cannot be granted through public registration, promotion
   requests, or RET Chair forms. Role, password, and account-status changes revoke
   existing sessions.
4. Start Flask and a separate supervised maintenance worker:

   ```text
   python scripts/system_worker.py
   ```

   A PostgreSQL advisory lock permits only one worker. Web workers no longer
   start APScheduler. Use the host's service manager with automatic restart.
   `--once` processes one queued job without scheduling new work. The dashboard
   reports missing/stale heartbeats instead of displaying healthy.
5. Sign in again. System Administrator lands on `/system/`; RET Chair lands on
   `/academic-overview`. Apply migrations before deploying the new code; missing
   maintenance state returns service unavailable.

Checking out this code provisions no real account. Tests use isolated databases
and never send real recovery email or clean up application uploads.

## Pages and access

| System Administrator page | Behavior |
| --- | --- |
| System Overview | Database reachability, worker heartbeat, latest backup, failed jobs, diagnostic results, and links to affected services. |
| Diagnostics | Queued checks for database/migrations, private storage, backup tools, and OCR. Email/public HTTPS remain explicitly not checked until tested externally. |
| Database Health | Database size, connection count/capacity, long-running query count, and migration status. Query bodies and SQL execution are not exposed. |
| Storage Maintenance | Storage usage/free space, missing references, and signed, expiring cleanup previews. |
| Backups & Recovery | Database/file bundles, SHA-256 verification, dedicated-database restore tests, and offline recovery instructions. |
| Scheduled Jobs | Queue/running/succeeded/failed states, timestamps, actor, reason, results, and supported retries. |
| Errors & Logs | Sanitized server request failures, request IDs, severity/time filters, pagination, and bounded JSON export. |
| Account Security | Suspend/reactivate approved accounts, clear lockouts, revoke web sessions, and queue recovery instructions to registered email. |
| Maintenance Mode | Immediate/scheduled downtime and a public notice; website requests receive HTTP 503 and Retry-After. |
| System Configuration | Allowlisted settings, deployment version, backup interval, and retention. Secrets remain server-managed. |
| Maintenance History | Durable maintenance/security events and job outcomes, actor, and reason. |
| My Account | Own account details, password, and contact information. |

RET Chair uses Academic Overview, Users & Roles, Capstone Repository, Requests,
Capstoner Review, Recycle Bin, Analytics & Reports, Academic Audit History, and
existing account pages. Academic URLs remain stable. System Administrators
cannot approve academic requests or read manuscripts. RET Chairs cannot access
maintenance or change System Administrator accounts. Technical reactivation
cannot approve a pending or rejected academic account.

## Server settings

Continue using existing database, mail, upload, and security environment variables.

| Variable | Purpose |
| --- | --- |
| `MAINTENANCE_BACKUP_ROOT` | Private directory outside web/static and upload directories; defaults to `backups/system`. Provide sufficient disk space and restricted filesystem permissions. |
| `MAINTENANCE_RESTORE_TEST_DB` | Explicitly provisioned disposable database on the configured PostgreSQL server. Its name must start with `capre_restore_test_` and differ from `PG_DB`. Tests replace its contents. |
| `PUBLIC_BASE_URL` | Trusted public HTTPS address used in recovery instructions. |
| `APP_VERSION` | Version or commit displayed in System Configuration. |

The worker schedules backups every 24 hours by default, diagnostics hourly,
and existing archive retention daily. Backup interval and retained bundle count
are editable. Orphan cleanup requires a preview, confirmation, and maintenance
mode; `UPLOAD_RETENTION_CLEANUP_ENABLED` no longer starts automatic deletion.

## Maintenance actions and recovery

Console mutation forms use CSRF protection and record a reason. Account security,
cleanup, restore tests, and maintenance-mode changes also require the operator's
current password. Browser input never becomes a shell command, SQL statement,
or arbitrary filesystem target.

Jobs are deduplicated. Worker restarts mark interrupted jobs failed instead of
silently replaying them. Cleanup requires a fresh preview rather than a generic
retry. File size, modification time, location, and references are rechecked.
Inspect a partly completed job before requesting another operation.

Backups include a PostgreSQL custom archive and private uploads. Database writes
wait during the SHARE-locked database/file snapshot; schedule backups for low
activity. Lock acquisition and PostgreSQL tools have timeouts. Copy failures do
not produce verified bundles. SHA-256 and `pg_restore --list` check integrity;
restoring into a dedicated test database is a separate recovery prerequisite.
Retention only removes older verified bundles and preserves the newest
restore-tested bundle. Arrange protected off-host copies through deployment.

Production recovery is offline:

1. Create a current safety backup; verify and restore-test the selected bundle.
2. Enable maintenance. Stop web and maintenance-worker services. Verify the
   configured database and upload-directory mapping.
3. Run `python scripts/system_recover.py --backup-id BACKUP_ID --confirm RESTORE --services-stopped`.
4. Recovery verifies the bundle again, restores the database in one transaction,
   restores files, revokes sessions, and leaves maintenance enabled. A receipt
   outside the database records success/failure. Newer, now-unreferenced files
   can be reviewed through a later cleanup preview.
5. On failure, keep services stopped. Inspect the receipt and protected server
   logs, correct the cause, and retry deliberately.
6. Restart services, inspect diagnostics and representative private documents,
   then end maintenance. Manual exit checks database and storage first.

Scheduled maintenance ends at its configured end time. Leave the end blank for
recovery or work with uncertain duration. The console needs a working database
to authenticate operators; database outages require host-level recovery access.

## Verification

```text
python -m pytest tests/test_system_administration.py tests/test_migration_runner.py tests/test_audit_logs.py -q
```

Before rollout, verify both login destinations, cross-role URL/POST denial,
migration/account mapping, password confirmation, worker restart, backup and
restore tests, cleanup previews, maintenance responses, and session
revocation. Record the chosen operator and recovery database outside source control.
