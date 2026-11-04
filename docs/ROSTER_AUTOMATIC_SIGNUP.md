# Student roster eligibility

## Scope and access

Active Admins and Capstone Professors use **Student Master Lists** (`/roster`).
Upload, history/results, search, record details and both template endpoints check
the current database role and account status. Student/Faculty/anonymous/inactive
accounts cannot browse roster data. CSRF protects uploads and confirmations.

Student registration retains COR PDF, consent, password policy for new credentials
and session-bound email ownership verification. Faculty registration retains its
faculty ID, verified email and manual review path. Public roles remain Student or
Faculty only; roster eligibility never grants staff roles.

## Files and templates

- Download `/roster/template/csv` or `/roster/template/xlsx` after signing in as an
  authorized uploader. A header-only CSV is also in
  `database/templates/student_master_list.csv`. Replace the XLSX example row.
- XLSX worksheets, DOCX tables, text-based PDF tables, or UTF-8 CSV (optional BOM).
  Multiple candidate worksheets/tables require explicit selection; tables are never
  merged across sheets, Word tables or PDF pages. Scanned/image-only PDFs require
  a text-based export; roster extraction does not invoke OCR or external AI.
  Legacy XLS/DOC, merged/nested data cells and ambiguous alignment are unsupported.
  No formulas or numeric
  spreadsheet cells for student numbers. Set identifier cells to **Text before
  entry**. CSV consumers such as Excel must import that column as text. Leading
  zeros are significant; scientific notation is rejected, never expanded.
- Limits: 5 MiB file, 30 MiB expanded Office archive, 10,000 extracted rows,
  40 columns, 64 tables/worksheets, 50 PDF pages. Parsing uses the existing isolated
  document worker with its memory/time/concurrency limits. Oversized,
  malformed, missing-header or duplicate-alias files are rejected before DB writes.
- Template headers: `university_num`, `user_first_name`, `user_middle_name`,
  `user_last_name`, `contact`. Middle name is optional. Header case, spaces,
  periods and hyphens normalize to underscores. `university_no`, `first_name`,
  `middle_name`, `last_name` and `email` are also accepted.
  Number aliases: `student_no`, `student_number`, `university_number`.
  Email alias: `email_address`. Other names/roles are not inferred from headers.
- Values trim whitespace; numbers uppercase, emails lowercase. Numbers allow
  ASCII letters/digits/hyphens, 1–50 characters. Names are display data, never an
  eligibility predicate. Blank first/last names and invalid emails are skipped.
- The first occurrence of a number wins, even if its row is invalid; subsequent
  occurrences are skipped. Results persist with source row numbers/reasons.
  Spreadsheet person/role columns never control the imported `Student` type.
- Repeated identical table headers are reported as skipped, never students.
  Every row retains worksheet/row, table/row or PDF page/table/row locations.
- Upload creates a private 30-minute preview, not an eligible upload. Preview shows
  mapped columns, extracted values, validation issues and estimated changes.
  Confirm rechecks claims and terms atomically. Only the opaque token and selected
  candidate are accepted from the browser; hidden records/counts are ignored.
- Necessary transient `roster_import_stage` stores extracted payloads, uploader
  and hashed session binding, expiry and a unique confirmation receipt. It has
  server-only RLS/revocations. Completion clears payload; retries return the same
  result. Expired stages are deleted on upload and by the delivery maintenance job.
  Raw documents use private temporary processing and are not stored in static.
- `uploaded_by` retains exactly the diagram attributes. `file_type=student_list`
  is the category; physical format, uploader and counts are recorded in audit.
  Results/history read that audit summary. No redundant user-to-roster column is
  added: account links are through `signup.user_id` and `signup.roster_id`.

## Imports and terms

Class is required. Academic year is exactly consecutive `YYYY-YYYY`, starting
between 1900 and 2200. Term order is numeric `(academic_year_start, semester_order)`:
**First=1, Second=2, Summer=3**. Free-form lexical labels never determine age.

Several uploads may be active for one term. Same-term, same-type, same-number rows:
identical details skip; unclaimed/unreserved differences update the existing row,
preserving roster ID and original upload link. Corrections audit before/after and
the new importing upload ID. Claimed/reserved/ambiguous records skip with reasons.

An import with additions/updates activates its upload and supersedes earlier active
student terms atomically. New terms insert new roster rows, including continuing
students. Existing accounts and historical links remain unchanged. Older-term
uploads fail. Zero-change imports persist as superseded result records and **do
not** supersede usable uploads. Any DB/audit failure rolls everything back.

## Automatic decisions and retry

One transactional lifecycle advisory lock coordinates imports, new signups,
resubmissions and reviewer/status activation safeguards. Matching locks roster and
upload rows; database uniqueness also protects absent identities. Import lookups
and inserts are batched; the lock intentionally serializes student transitions.

In one transaction a student application consumes a currently valid email proof,
creates pending account/signup state, and decides against a **unique active
Student roster row with the same normalized number AND verified email**. Other
account claims and other pending reservations fail closed. Names do not match.

Approval sets user active with Student role looked up by name. Signup records
approved/auto, unique approved roster claim, contact link, student subtype, timestamps,
NULL reviewer and an audit decision. Nonmatch creates a rejected/auto decision with
internal reason, rejected user and no roster claim. Public messages never identify
another applicant. No manual request is created for an automatic decision.

Use `/signup?resubmit=1` for an explicit rejected-student retry: existing username
and password, newly verified **same account email**, COR, and corrected details.
It reuses the account/credentials, permits a corrected unclaimed student number,
and adds a new signup decision without reopening/overwriting earlier decisions.
Legacy passwords remain valid for authentication; resubmission does not set a new
password. New passwords still use the existing 8–12-character policy. A new list
never automatically reopens/re-evaluates rejected signups.

Duplicate-account attempts use sign-in/recovery/resubmission guidance; no second
account is created. Conflicting ownership needs explicit administrator identity
resolution, never automatic merges. Existing active accounts without roster links
stay active. Existing pending student requests remain unchanged. Manual approval
and ordinary activation cannot bypass roster checks; an explicit manual rejection
allows the student to use the validated resubmission path. No bulk re-evaluation
occurs. Faculty manual reviews remain supported. COR is still collected, while
verified roster matching is the authority for new student approval.

## Decision delivery

The decision transaction inserts a private `signup_decision_delivery` row. HTTP
signup attempts delivery **after commit**. SMTP failure leaves approval/rejection
intact and schedules retry after 15 minutes. Messages use the existing account
email template; logs contain delivery IDs, not passwords, OTPs or roster contents.

Run `python scripts/deliver_signup_decisions.py` periodically, e.g. every five minutes
under the deployment scheduler. It purges expired stages and processes up to 25
due messages per invocation;
concurrent workers use SKIP LOCKED. The worker initializes only Flask/mail config,
not the web app's archive-purge scheduler. Configure the existing SMTP settings.
Delivery is **at least once**: a worker/network failure after SMTP acceptance but
before delivery-state commit may send a duplicate on retry. Queue rows contain
private recipient snapshots and retain existing server-only RLS/revocation rules.

## Migration and preflight

New additive migration: `20261106_roster_auto_signup.sql`. Historical migrations,
including applied `20261104` and `20261105`, are unchanged. Fresh reference schema
is synchronized; normal fresh setup still uses immutable original + migration runner.

Run preflight read-only before scheduling migration:

```sql
SELECT UPPER(BTRIM(university_no)) AS normalized_number, COUNT(*)
FROM "user" WHERE NULLIF(BTRIM(university_no),'') IS NOT NULL
GROUP BY 1 HAVING COUNT(*) > 1;
SELECT upload_id, status, academic_year, semester FROM uploaded_by;
SELECT roster_id, status, COUNT(*) FROM signup
WHERE status IN ('pending','approved') AND roster_id IS NOT NULL
GROUP BY 1,2 HAVING COUNT(*) > 1;
SELECT upload_id, UPPER(BTRIM(university_no)), COUNT(*) FROM roster
GROUP BY 1,2 HAVING COUNT(*) > 1;
SELECT roster_id FROM roster WHERE person_type IS NULL
 OR person_type NOT IN ('Student','Faculty')
 OR NULLIF(BTRIM(university_no),'') IS NULL OR NULLIF(BTRIM(contact),'') IS NULL;
```

Resolve conflicting account numbers, pending/approved claims, duplicate rows and invalid historical
roster values by explicit reviewed policy; do not silently delete/merge accounts
or fabricate identities. Pending/unclassified historical uploads cause migration
failure. An owner-reviewed data remediation may explicitly mark historical uploads
superseded, preserving records but disabling eligibility. Unknown term/list/uploader
metadata may remain NULL only on superseded history; re-import an actual current
verified list through the service after rollout. Active uploads require complete
metadata. No historical upload is automatically activated or reclassified.

During this implementation, read-only inspection found **14 applied migrations,
no existing uploads, and one normalized account-number conflict group** in the
configured database. The new migration was **not run there**. That conflict is a
deployment blocker requiring explicit data resolution. No cleanup was performed.

After preflight resolution, rehearse on a disposable/restored test database, stop
legacy signup/import writers for cutover, apply via the normal migration runner,
deploy matching backend/assets, then enable uploader access and the delivery worker.
Do not deploy the new signup path against an unmigrated database. Confirm claims,
manual faculty/legacy pending behavior, COR requirements, role restrictions and SMTP.

## Verification

Meaningful PostgreSQL tests cover imports/parsing, permissions/CSRF, row protection,
atomic rollback, terms, claims/reservations, concurrency with supersession, proof
consumption, approved/rejected fields, explicit retry and post-commit delivery failure.
Existing tests now explicitly seed historical manual accounts rather than assuming
new public students enter manual review.

- `python -m pytest -q`: **491 passed, 3 skipped**, 639.42 seconds. Browser fixtures
  run their local app servers. The three skips require `CAPRE_TEST_POSTGRES=1`
  (two keyword-normalization cases and one Supabase setup case); that opt-in was
  left disabled to avoid using the configured database.
- Final `python -m pytest tests/test_student_documents.py -q`: **23 passed**,
  47.47 seconds, including later worksheet-separation, HTTP tampering, legacy
  approval safeguards and both fresh-schema RLS checks.
- Route-contract/extraction checks: **31 passed** before the final additions.
  `compileall` and `git diff --check` pass.
- Migration runner, transactions and fresh schemas were verified only in disposable
  local PostgreSQL databases. Live SMTP delivery and production migration were
  not exercised; delivery success/failure/retry were tested with controlled mail.

No production migration, commit or push was performed.
