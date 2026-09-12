# CAPRE production readiness contract

This document is the acceptance contract for the complete CAPRE capstone
repository and user-management system. The `aresVer` branch remains
experimental until every release gate below is satisfied.

## Functional acceptance

| ID | Workflow | Production behavior |
| --- | --- | --- |
| CAP-01 | Account access | Users can register, verify their email/OTP, sign in case-insensitively, reset passwords, and receive verification decisions. |
| CAP-02 | COR verification | Signup validates the COR file, extracts the supported fields, rejects unsupported year levels, and lets an authorized admin review the private document. |
| CAP-03 | Role access | Students, faculty, capstone professors, and admins can access only their permitted routes and records. |
| CAP-04 | Repository | Authorized users can create, update, search, archive, view, request, and cite capstone records. |
| CAP-05 | Author identity | A capstone author may remain unlinked to a user account. Linking is explicit, scoped to one author credit, audited, and never inferred from a matching name. |
| CAP-06 | Similarity | Topic similarity uses title text only, uses the documented TF-IDF behavior, and returns safe results for empty, short, invalid, and duplicate titles. |
| CAP-07 | Capstoner workflow | Students submit registration; eligible registrations are reviewed by a capstone professor; approval and author assignment remain separate actions. |
| CAP-08 | Advisory roster | Active capstone professors can create and rename groups, add at most four verified students, and remove roster membership without changing account, registration, or authorship state. |
| CAP-09 | User profile | Users can view their identity, linked works, contacts, role status, COR status, and profile image. |
| CAP-10 | Author activity | The system records deduplicated views, citations, and requests, calculates author totals, and sends privacy-safe notifications to linked authors. |
| CAP-11 | Administration | Admins can review accounts, verification requests, capstoner requests, audit history, and analytics with summarized and filterable results. |

## Data and privacy rules

- Account users and repository authors are separate identities. `author.user_id`
  may be null until an authorized person explicitly links it.
- Private COR files and avatars are never served from a public static path.
- Requester identity is not exposed in author activity notifications.
- The activity actor is excluded from author notices; linked coauthors can
  still receive the privacy-safe event.
- Every administrative decision, role change, author link, roster change, and
  private-file action is attributable to an authenticated actor.
- Deleting an account must follow documented retention and foreign-key rules;
  it must not silently delete an unrelated author credit or capstone.

## Release gates

1. All migrations run successfully on a clean database and an upgrade database.
2. Migration application is tracked and repeatable; backups and restore are tested.
3. Unit, PostgreSQL integration, browser, authorization, CSRF, XSS, upload,
   concurrency, and privacy tests pass with zero failures.
4. Debug mode is off; secrets come from environment configuration; cookies,
   HTTPS, CSP, rate limits, logging, and error handling are production-safe.
5. Email, OCR, private-file storage, database failure, and background work have
   observable failure paths and do not corrupt saved decisions.
6. The final ERD, DFD, database migrations, UI behavior, and tests describe the
   same workflows.

## Current blockers on `aresVer`

- Activity schema, deduplication, author totals, privacy-safe bell
  notifications, PostgreSQL integration coverage, author-bell browser
  coverage, and request/view/citation route coverage are implemented on this
  branch.
- The latest full local test run has 255 passing and 2 skipped tests. The skips
  are external E2E checks that require a separately running server at
  `localhost:5000`; they are not counted as a production pass.
- Migration tracking, backup/restore commands, non-destructive backup archive
  verification, and read-only health probes are implemented. Backup/restore
  execution in the target environment, automatic retention cleanup
  configuration, and deployment environment verification are still pending.
- Manuscript uploads now validate size and file signatures. Orphaned private
  files can be reviewed with a read-only report and removed after the approved
  30-day retention period. Automatic deletion remains opt-in.
- Optional ClamAV-compatible scanning is wired into COR, manuscript, and avatar
  uploads. Production must configure the scanner and require it before this
  upload gate is complete.

Monitoring, deployment preflight, and the local regression gate are
implemented. The next implementation step is verifying the production
deployment environment, backup/restore procedure, scanner, mail delivery,
and external E2E workflow. No feature is production-complete until the
relevant acceptance row and release gate are both satisfied.
