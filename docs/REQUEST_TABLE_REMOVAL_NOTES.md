# Legacy manuscript workflow retirement

## Dependency matrix

| Dependency | Former behavior | Revised behavior / regression coverage |
| --- | --- | --- |
| `app/db/requests.py`; pages manuscript creation, cancellation, status/history routes | SQL against `request`, approval-derived access | Deleted services and routes; retirement tests require 404, students receive 403 for full readers/files |
| `app/routes/admin/requests.py`; request list/sidebar/filter UI | Admin manuscript decisions | Removed blueprint import, handlers, templates, scripts and navigation |
| `app/db/capstone_requests.py`; archive rankings/API | Submission counts and popularity | Removed service, ranking page/API, navigation and ranking styles |
| `app/routes/decorators.py`; manuscript reader and file routes | Independent staff roles plus student approval | Current DB user required; Admin/Faculty/Capstone Professor retain reading; students abstract-only; original files remain Admin-only |
| Archive cards, sidebar and dialogs | Approval flags and request buttons | Removed approval queries, flags, forms and JS; archive search/filter/citation retained |
| `app/db/qol.py`; main context, header/navbar | Request decisions, notification reads, pending counts | Removed service, route, notification menu/script and request badges |
| Auth signup/reapplication; admin verification; private COR reads | Verification rows shared `request` storage | Existing `signup` review fields used; UI compatibility aliases identify signup records; account emails retained |
| Existing pending signups with NULL metadata | Historical account status in user row | Fallback to existing pending account status; review updates signup atomically; dedicated regression tests |
| Admin review history | Shared request decision records | Removed route, service, template and Manage Users links; generalized audit retained |
| Audit summaries/categories | Manuscript-specific labels/filter group | Removed manuscript actions and empty Requests category; existing audit rows retained as Other |
| Capstone/user deletion | Clear/delete request FKs | Removed obsolete SQL; retained audit, signup and credential cleanup |
| Seeders and setup | Seed requests and recreate tables | Removed request seeds/truncation entries; fresh setup replays immutable original + historical migrations + retirement |
| Tests | Ranking/layout/request quota/query-plan assertions | Retired feature tests removed; retained keyword concurrency, pool/timeouts, auth, profile, audit, archive tests; new absence/security/migration tests |

## Removed and retained behavior

Removed manuscript applications, approvals/rejections, resubmission/cancellation,
request history, popularity counters, request notifications and queues.
Retained login/logout, password reset, signup/email ownership, COR verification,
roster/signup schema, contact verification, repository, author management, search,
citations, capstone view history, publication analytics, and generalized audit.

The old `/manuscript/view/<id>` URL remains a guarded reader for independent
privileged roles. It returns 403 for students, including former approved students.
Rendered page routes also return 403; original file routes remain Admin-only.
No replacement student entitlement has been invented. Restoring student full
reading requires a separate owner-approved access policy.

## Initial configured database: read-only inspection

On 2026-11-04, `schema_migration` contained 13 applied migrations through
`20261104_roster_signup_revision.sql`. Retirement was not recorded.
`public.request` contained **9 rows**; `public.capstone_requests` contained
**7 rows**. Normal external dependencies reported by `pg_depend` were empty
for both tables at inspection time. This is a snapshot, not a deployment guarantee.
Read-only checks also found zero pending accounts without signup rows, zero users
with duplicate signup rows, and zero pending signups needing the NULL-status fallback.

At that initial inspection, no migration, deletion, truncation, export or backup
had been performed. The guard correctly rejected populated tables. Historical
account verification decisions also required a retention decision because they
shared the retired request table. The subsequent approved action is recorded below.

The pending retirement migration retains both row guards and `RESTRICT`. Since
it was verified unrecorded, it now locks each table before counting to prevent a
concurrent insert between checking and dropping. All previously applied migration
files and `database/capre_original_final.sql` remain unchanged. The revised schema
initially still declared the retired tables; those declarations were removed.
No `database/capre_revise.sql` alias was present in this checkout.

## Approved deletion and completed migration

The owner subsequently explicitly approved permanently deleting the 9 `request`
rows and 7 `capstone_requests` rows without creating a backup, including any
account-verification history stored there. No backup or export was created.

Preflight reconfirmed those exact counts, only the retirement migration pending,
matching historical checksums, and no incoming foreign keys, custom triggers or
external dependencies on either retired table. Both tables were locked, the 16
approved rows deleted, and `scripts.migrate.main(['upgrade'])` executed using the
unchanged project runner. Its internal commits were deferred on the same connection
so cleanup, table drops and migration tracking committed as one transaction only
after verification. Errors or changed approval counts would roll back the operation.

The recorded application timestamp is **2026-11-04 21:57:57.782608 +08:00**.
Independent committed-state checks confirmed both tables absent, the retirement
checksum matching the unchanged SQL file, and retained account/repository tables
present. All **23 retained public tables** had unchanged row counts across the
transaction; migration bookkeeping gained the retirement record.
`python scripts/migrate.py status` reports **14 applied, 0 pending**.

The 16 deleted rows were not archived or preserved by this operation. The prior
historical-row deployment blocker is resolved for this configured database.

## Verification

- Python compilation (`python -m compileall -q app scripts tests`) passed.
- JavaScript syntax (`node --check app/static/js/archive_sidebar.js`) passed.
- All HTML templates parse; all literal `url_for` endpoints exist.
- No active SQL references to either retired table remain in application,
  seeder/maintenance scripts or fresh setup SQL. Immutable historical SQL and
  migration safety tests intentionally retain their references.
- The immutable original and all 13 historical migrations have no Git content
  changes; all 13 configured database checksums match repository bytes or the
  migration runner's accepted LF/CRLF equivalents.
- Targeted retirement, route-contract and protected-reader run: **66 passed** in
  139.38 seconds, including disposable PostgreSQL row guards, RESTRICT rollback,
  retained view-history data and normal-runner checksum/idempotency checks.
- Restored original-feature/account/browser module: **33 passed** in 109.81 seconds.
- Full regression: `python -m pytest -q --tb=short -rs -p no:cacheprovider
  -o faulthandler_timeout=90` — **424 passed, 3 skipped** in **734.47 seconds**,
  exit code 0. No failures or errors. The interpreter was the workspace venv.
- Two parameter cases in `tests/test_keyword_normalization.py:40` and one test
  in `tests/test_supabase_setup.py:56` were skipped with the exact reason:
  `Set CAPRE_TEST_POSTGRES=1 for isolated PostgreSQL checks`. These opt-in tests
  connect using configured database credentials; the flag was deliberately left
  unset. New retirement tests use separately created disposable databases.
- Owner-reported baseline: 442 passed, 3 skipped; not independently rerun before
  editing. Retired feature tests were replaced with 22 absence, authorization,
  signup compatibility and migration safety cases. Unrelated browser, password,
  profile and account verification coverage was retained.
- Initial sandbox runs could not access pytest temp directories/start PostgreSQL;
  successful verification runs used approved execution outside the sandbox.
  Browser tests provided Flask adapters or their own loopback server. Earlier
  stale request assertions and an over-broad test edit were corrected before the
  final full run; no known failing checks remain.

## Backend alignment audit after migration

Read-only inspection of the configured database found all **23 target tables**
and **149 target columns** matching the revised schema by name, PostgreSQL type
and nullability. The only extra table is expected infrastructure,
`schema_migration` (four columns). All **14 migrations** are recorded with matching
checksums; none are pending. `request`, `capstone_requests` and `logout` are absent.

PostgreSQL successfully prepared **147 static backend SQL statements**, including
write statements, without executing their writes. **49 complete backend read
checks** also passed using database-enforced read-only connections, covering
repository/search/sorts, archive, authors, users/profiles, signup review/COR
lookups, view history, audit filters and analytics with/without a year filter.
Concatenated audit SQL and analytics parameter inference were checked through
those complete runtime calls; no schema-breaking query errors were found.
No live data or database schema was changed during this audit.

Targeted regression command:
`python -m pytest -q tests/test_request_retirement.py tests/test_auth_security.py
tests/test_roster_signup_revision.py tests/test_database_performance.py
tests/test_creation_transactions.py --tb=short -p no:cacheprovider`
returned **57 passed** in **146.96 seconds**, exit code 0, using disposable
PostgreSQL databases. Python compilation also passed. The prior full-suite result
of 424 passed / 3 opt-in skips remains recorded above; it was not rerun for this
read-only audit because no backend implementation changed.

**Compatibility is not full ERD workflow implementation:** the nullable roster
entities exist, but application code has no roster upload/import/matching workflow.
Signup inserts `user_id`/`registration_date` and writes review metadata, but does
not populate `signup.roster_id`, `signup.contact_id` or `signup.method`.
These omissions do not break current signup because the columns are nullable.
Roster-driven signup would require separate implementation; this audit did not
invent matching rules or change existing registration/access behavior.

## Deployment checklist for other installations

The configured database completed retirement as recorded above. These steps apply
to other installations; the owner's explicit no-backup deletion approval applied
only to the verified 9 and 7 rows in this database.

1. Keep deployment blocked on the 16 historical rows. Obtain and verify a backup,
   export/retention destination, and explicit owner approval for any destructive
   cleanup. Do not bypass guards or silently discard verification history.
2. Resolve retention and preserve any required account decision history. Existing
   pending signups remain reviewable from signup/user state; examine missing or
   duplicate historical signup records before cutover.
3. Stop legacy writers and take the application offline for cutover. Deploy this
   revision and execute `python scripts/migrate.py status`, then the normal
   `python scripts/migrate.py upgrade` only when authorized and both tables are
   legitimately empty. Recheck recorded migration state before using any edited
   pending file; never change an already recorded checksum.
4. If `RESTRICT` fails, inspect the actual dependency and explicitly revise it;
   never substitute `CASCADE`. Migration failure must leave no retirement record.
5. Confirm both tables absent, retained tables/data present, and the retirement
   checksum recorded. Smoke-test signup/review, auth, student abstract-only access,
   staff readers, Admin files, archive links, citations and retained analytics.
6. Resume traffic only after these checks. Where a reviewed backup exists, rollback
   requires restoring it and the matching application revision during maintenance.
   No backup was created for the approved operation above; this operation provides
   no recovery copy of the deleted rows. Do not run legacy code against a retired schema.

## Changed source inventory

Inventory generated at completion below; unrelated pre-existing Kanban artifacts
were left untouched. `scripts/data_seeder.py` is ignored/untracked in this checkout
but its local legacy workflow was also removed.

<!-- inventory -->

- `.gitignore`
- `app/constants/nav.py`
- `app/db/archive.py`
- `app/db/audit_reader.py`
- `app/db/auth.py`
- `app/db/capstone_requests.py`
- `app/db/database.py`
- `app/db/qol.py`
- `app/db/requests.py`
- `app/db/review_history.py`
- `app/db/users.py`
- `app/db/verification_documents.py`
- `app/routes/admin/__init__.py`
- `app/routes/admin/requests.py`
- `app/routes/admin/users.py`
- `app/routes/authentication/sessions.py`
- `app/routes/decorators.py`
- `app/routes/main.py`
- `app/routes/pages/archive.py`
- `app/routes/pages/manuscripts.py`
- `app/static/css/pages/_all-requests.css`
- `app/static/css/pages/_archive.css`
- `app/static/css/pages/_manuscript-request.css`
- `app/static/js/archive_sidebar.js`
- `app/static/js/notifications.js`
- `app/static/js/request_sidebar.js`
- `app/static/js/requests_filter.js`
- `app/templates/admin/_request_list.html`
- `app/templates/admin/manage_users.html`
- `app/templates/admin/requests.html`
- `app/templates/admin/review_history.html`
- `app/templates/authentication/signin.html`
- `app/templates/authentication/signup.html`
- `app/templates/base.html`
- `app/templates/global/all_requests.html`
- `app/templates/global/explore_archive.html`
- `app/templates/global/most_requested_capstones.html`
- `app/templates/index.html`
- `app/templates/partials/header.html`
- `app/templates/partials/most_requested_capstones.html`
- `app/templates/partials/navbar.html`
- `app/templates/partials/request_purpose.html`
- `app/utils/audit_summary.py`
- `app/utils/auth_rate_limit.py`
- `database/capreDB.sql`
- `database/capre_revised_schema.sql`
- `database/supabase_setup.sql`
- `docs/REQUEST_TABLE_REMOVAL_NOTES.md`
- `migrations/20261105_remove_legacy_request.sql`
- `scripts/data_seeder_current.py`
- `scripts/setup_supabase.py`
- `tests/fixtures/database_queries_before.json`
- `tests/fixtures/route_contract.json`
- `tests/locustfile.py`
- `tests/test_account_sms.py`
- `tests/test_auth_security.py`
- `tests/test_dark_readability.py`
- `tests/test_data_seeder_current.py`
- `tests/test_database_performance.py`
- `tests/test_manuscript_reader.py`
- `tests/test_most_requested_capstones.py`
- `tests/test_my_requests_layout.py`
- `tests/test_original_branch_features.py`
- `tests/test_request_retirement.py`
- `tests/test_roster_signup_revision.py`
- `tests/test_route_contract.py`
- `tests/test_spam_prevention.py`
- `tests/test_workflow_updates.py`
