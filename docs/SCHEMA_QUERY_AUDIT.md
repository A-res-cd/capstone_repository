# CAPRE schema/query compatibility audit — 2026-11-04

This audit preserves the existing application behavior. The configured database
was accessed only in PostgreSQL read-only transactions for schema metadata,
migration history, and PREPARE/DEALLOCATE validation. No application data was
changed or reset, and no migration was run against that database. Runtime tests
use newly initialized local PostgreSQL clusters and disposable databases.

## Actual schema findings

The public schema contains 26 tables and 169 columns, including the migration
tracking table. Comparing metadata with a fresh isolated database created from
`database/capre_revised_schema.sql` found no missing/different application
columns, defaults or nullability, no missing constraints, and no missing required
indexes. Exact column types and lengths also match. The four extra
columns and five extra constraints belong to `schema_migration`; 14 additional
index definitions come from historical migrations and tracking. There are 126
catalog constraints and 49 indexes in total. Catalog constraints include
PostgreSQL NOT NULL entries, in addition to keys and checks.

Verified tables: audit, auth_rate_limit, author, capauth, capstone,
capstone_keyword, capstone_requests, capstone_view_history, contact,
contact_changes, kappa, keyword, login, password_reset, program, request, role,
ror, roster, schema_migration, signup, signup_email_verifications, slug,
specialization, uploaded_by, and user.

- `uploaded_by`: required file name; pending status and timestamp defaults; PK
  `upload_id`. No invented uploading-administrator link.
- `roster`: PK `roster_id`, required `upload_id` FK with DELETE RESTRICT; upload,
  university number and lower(contact) indexes. University numbers are not unique.
- `signup`: existing user FK and registration_date remain. Optional roster,
  contact and reviewer FKs are present; attempt_count is nonnegative, NOT NULL,
  default 0. All four FK indexes and the status/requested_at index exist.
- `logout` is absent. Application logout writes to `audit`; archived historical
  events and live events do not require a logout table.
- `roster` and `uploaded_by` both have row-level security enabled.

All 13 migration names are recorded, with no missing or pending names. Initially,
the local revision file did not match its recorded checksum; the difference
removed historical archiving, RLS/revocation and the signup user index. With the
user's explicit approval, the local file was restored byte-for-byte to the earlier
applied version. Its SHA-256 now equals the recorded value:
`39e60b79b43eeac6dfb78c2bcb80af6407b10cd858cbdd47465a650353fdb861`.
Neither database history nor the applied SQL definition was changed. All other
historical checksums match the runner's raw/LF/CRLF equivalence rules.

## Query inventory and compatibility matrix

Repository-wide SQL search found 1,015 SQL-bearing lines before repair. AST
inspection after repair identified 507 execute/executemany sites in 38 Python
files: 197 in the app, 72 in scripts (including the ignored local legacy seeder),
and 238 in tests. Of the app/script sites, 240 literal DML/SELECT statements were
successfully PREPARE-validated in a read-only connection without executing them;
seven need explicit integer parameter types for PostgreSQL's PREPARE inference.
These seven use year/ID parameters that psycopg2 normally adapts as values, so
the initial inference errors were not schema defects. The remaining 29 sites
are composed queries, transaction statements, schema setup or migration loading;
their SQL fragments and dependencies were reviewed separately. Test SQL uses
isolated fixtures, including intentional pre-migration logout rows.

| File/query | Finding | Correction or disposition |
| --- | --- | --- |
| `app/routes/authentication/sessions.py::get_current_user` SELECT | **Confirmed error:** `user.first_name`, `middle_name`, `last_name`, `email` do not exist. PREPARE failed on `u.first_name`. | Select `user_*_name` with the original result aliases; read email from contact using a deterministic primary-first subquery. Real PostgreSQL regression test added. |
| `app/db/auth.py::create_user` INSERT signup | Correct: user_id and registration_date remain supported. New optional links can be NULL; attempt_count has a default. | Preserve current registration; do not guess a roster/contact association. |
| `app/db/auth.py::sign_out`, `app/db/audit.py` INSERT audit | Compatible with removed logout table; current activity references user and stores device IP. | No new change needed. E2E verifies audit persistence after logout. |
| `app/db/users.py` account deletion and user listing | Correct current name/contact joins. Reviewer/contact links are cleared before parent deletion; no logout DELETE. | Preserve existing behavior; revised-schema deletion tests cover this path. |
| `app/utils/auth_utils.py` session user SELECT | Correct user name, role, current credential and account-status columns. | Preserve real session validation; E2E uses this loader. |
| `app/db/audit_reader.py` count/page SELECTs | Intentionally excludes login/logout before applying category, date and search filters. LEFT JOIN preserves deleted/unknown actors. | Preserve product behavior; fix the stale test seed and explicitly test exclusion. |
| `app/db/archive.py`, `app/db/capstones.py` composed SELECTs | Keyword aggregate, program/track joins, filters, allowlisted sorting and pagination use existing columns. Archive INNER JOINs require complete program/track seed links. | Complete E2E fixture relationships; do not loosen production joins to accommodate incomplete test data. |
| `app/db/keywords.py` keyword replacement | Normalized keyword/capstone_keyword relationships remain valid. | No change. |
| `app/db/analytics.py` aggregate/report SELECTs | Current program/track/year/status columns exist. Six PREPARE statements need integer year/ID parameter declarations. | Typed PREPARE succeeds; no query change needed. |
| `app/db/capstone_requests.py` INSERT/ranking SELECT | capstone/user/time relationships and ranking joins remain valid. One PREPARE needs integer ID parameter declarations. | No query change. |
| `app/db/requests.py`, `app/db/review_history.py` request queries | Use existing request.user_id/reviewed_by and current user names. These are request approval links, independent of new signup review metadata. | No change. |
| `app/db/qol.py` dashboard/notification SELECT | Existing request decisions and capstone joins remain valid, including admin-only composed counts. | No change. |
| `app/db/contact_changes.py`, `app/db/signup_verification.py` ownership-code SQL | Existing contact_changes/signup_email_verifications schema remains available. These are distinct from signup review records. | No change. |
| `app/db/profile_settings.py`, `verification_documents.py`, `view_history.py` | Avatar, COR review, and capstone view fields/relationships remain valid. | No change. |
| `app/utils/auth_rate_limit.py`, `document_processing.py` SQL | Rate-limit and verification checks use existing infrastructure tables. | No change. |
| `app/db/migration_runner.py`, `scripts/setup_supabase.py` | Runner tracking and revised fresh-schema setup remain compatible. Local revision content initially drifted from applied checksum. | Restore exact applied bytes after explicit user approval; do not rewrite tracking or rerun live migrations. |
| `scripts/data_seeder_current.py`, ignored `scripts/data_seeder.py` | Registration INSERTs remain valid; truncate lists no longer reference logout. | No query change in this audit. These destructive tools were inspected, never run on the configured database. |
| `scripts/backfill_abstracts.py` | Current abstract/file columns exist. | Read-only PREPARE validation; no backfill executed. |
| Routes/services and other utility scripts | No additional embedded SQL execution sites beyond the modules listed above. | Existing helpers supply data access. |
| `database/*.sql`, historical migrations, test fixture SQL | The immutable original schema and migration tests intentionally contain the old logout storage. Active setup uses revised schema plus tracked migrations. | Keep historical definitions; do not recreate logout in the running application. |

## Root cause of the five reported failures

The original targeted command reproduced all five failures before edits:
`python -m pytest tests/test_e2e_workflow.py tests/test_cor_pdf.py tests/test_original_branch_features.py::test_audit_filters_and_safe_details -q`.

1. `test_signin_search_logout`: hard-coded localhost:5000 had no running server,
   producing ERR_CONNECTION_REFUSED before database logic. The stale test also
   used email instead of username, an unseeded account, a password beyond the
   current limit, and obsolete search/card selectors. It now starts a real
   loopback Flask server over a disposable revised database, seeds complete
   account/capstone relationships, uses current selectors, and verifies audit
   persistence plus protected-page redirection after logout. No app SQL is mocked.
2. `test_signup_validation`: the same unavailable server, plus outdated
   university_number/error selectors that no longer describe the signup wizard.
   It now exercises the current required-COR validation and verifies the wizard
   cannot advance, then submits a complete form with invalid student_no through
   the server and verifies the original ID-format rejection without account
   creation. It uses the same self-managed server prerequisite.
3. `test_sample_cor_pdf_is_readable_and_image_based`: a private user upload was
   missing. Replace it with an in-memory synthetic, one-page image-only PDF;
   retain the image-count/no-text-layer assertions. Rendering was visually checked.
4. `test_sample_cor_extracts_expected_fields_when_ocr_is_available`: the same
   missing private upload. Use the synthetic fixture and assert its fake identity
   fields after real OCR. Skip only when the OCR dependency is unavailable;
   unexpected extraction warnings fail rather than being hidden by a skip.
5. `test_audit_filters_and_safe_details`: insertion and commit worked. The pooled
   connection's context manager commits before returning the connection, and
   another connection can read the inserted rows. The test seeded 27 login rows,
   while the reader always excludes login/logout. Therefore zero, not 27, is the
   correct old query result. The half-open date filter includes September 10 and
   excludes the unknown September 11 event; it was not the cause. The revised
   test seeds 27 visible signup events, one unknown event at the date boundary,
   and two deliberately hidden auth events. It checks committed count 30,
   account count 27, page 99 clamped to 2 with two events (page size 25), unknown
   actor display, payload redaction, auth-event exclusion and literal search.

## Files changed in this audit

- `app/routes/authentication/sessions.py`: repair the confirmed SELECT while
  preserving its result keys and existing logout behavior.
- `tests/test_e2e_workflow.py`: self-managed isolated server/database, real session
  loader, seeded relationships, current selectors and logout checks.
- `tests/test_cor_pdf.py`: synthetic scanned fixture and explicit OCR availability.
- `tests/test_original_branch_features.py`: correct audit event fixture and add
  transaction visibility/auth-exclusion assertions.
- `tests/test_roster_signup_revision.py`: real PostgreSQL regression for the helper.
- `migrations/20261104_roster_signup_revision.sql`: restore only exact applied bytes,
  approved by the user and verified against recorded SHA-256; no new migration SQL.
- `tests/README.md`, these audit notes, `.gitignore`: testing prerequisites,
  compatibility findings, and allow this report in version control.

## Validation and remaining limits

Final targeted repair run: **6 passed in 101.95 seconds**, covering all five
reported failures (including the original invalid-ID check) and the new helper
regression. The live metadata/reference comparison passed separately: **1 passed
in 21.31 seconds**. Full regression: **442 passed, 3 skipped in 696.33 seconds**.
The baseline reproduction had **5 failed**. Python syntax and git diff --check
validation also passed.

Full command: `venv/Scripts/python.exe -m pytest -q --tb=short --show-capture=no -p no:cacheprovider --basetemp=.test-tmp-query-full`.
The three skips are the two parameterized keyword-schema checks and the Supabase
SQL check gated by CAPRE_TEST_POSTGRES=1. Those opt-in tests connect using Config,
so they were left disabled rather than allowing writes to the configured
database. Dedicated revision/fresh-setup tests ran in disposable databases.

Run from the repository root with `venv/Scripts/python.exe -m pytest -q` (Windows)
or the equivalent activated environment. `initdb`/`pg_ctl` must be on PATH;
install browser binaries with `python -m playwright install`. No external Flask
server is required. Tests own and clean up loopback servers and disposable
databases. On a restricted Windows sandbox, allow local PostgreSQL processes
and use a fresh writable pytest --basetemp directory when needed.

Read-only PREPARE checks validate relation/column/type compatibility, not every
business branch or a deployment. Runtime validation used isolated databases,
never the configured live data. No new roster import/review workflow, authentication
redesign, schema revision, production migration or live-data mutation was performed.
No confirmed schema/query incompatibility remains; the three opt-in configured-
database tests are the remaining validation limit. Temporary schema metadata,
generated PDF previews, local servers and test databases were cleaned up.
