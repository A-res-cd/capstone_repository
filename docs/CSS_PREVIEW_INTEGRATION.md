# Selected aresver-css integration

Branch: `integrate/aresver-css-preview`, based on `aresVer`. This is a selective
integration, not a full Git merge of `aresver-css`.
Source snapshots: `aresVer` at `a64ab6d`, `aresver-css` at `45378b8`.

- Adds repository/archive search controls, publication status, cached abstracts,
  program/specialization codes and BSDS choices, and title/abstract/keyword matching.
- Adds the watermarked PDF reader, student viewing history, and review history.
  Capstone Professors see their own completed reviews; RET Chairs see all reviews.
- Imports compatible repository, archive, analytics, authentication and form styling.
- Preserves RET Chair/System Administrator separation, current manuscript download
  permissions, saved capstones, comparison, promotion requests, author-account
  links, activity tracking, advisory/progress, and system administration.

Before running this version against an existing database, back up the database
and uploads, then apply pending migrations with `python scripts/migrate.py upgrade`.
The new migration is `20261005_css_preview_repository.sql`; it adds columns,
history and indexes without dropping tables or changing roles. Existing publication
statuses remain NULL until reviewed; new capstones default to unpublished.
Then run `python scripts/backfill_abstracts.py` to cache available existing abstracts.
These commands have not been run against the configured application database.
Fresh installations also need the pending migrations after the bootstrap schema.

The full merge still needs decisions about incoming Admin-role permissions,
original-file download restrictions, saved-capstone deletion, promotion removal,
and overlapping account/authentication processes. Preserve existing migrations
and role records while resolving those differences.

Validation: 83 selected integration/browser tests and 32 retained-feature tests
pass. Python compilation and Git whitespace checks pass. The full suite stops
on existing advisory-page browser failures (`profile` is undefined); the same
failure was reproduced on untouched `aresVer` at `a64ab6d`.
