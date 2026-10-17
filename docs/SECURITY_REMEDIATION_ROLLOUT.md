Recovery changes require the current password and proof of the new destination.
Document validation and OCR run in bounded subprocesses with shared admission.

Apply migrations before deploying the routes: `python scripts/migrate.py`.
The contact-change table deliberately leaves existing contacts' `verified_at`
unset. Existing recovery behavior remains available; replacements require both
the current password and a separately delivered code. Removal is refused; users
can verify a replacement. Change one destination at a time.

Check configured SMTP and Semaphore delivery in staging, including provider
failure and notification failure. Contact codes expire after 15 minutes and five
failed attempts. Account/IP limits and hashed destination limits use PostgreSQL.
Old password-reset proofs are invalidated atomically on confirmation.

Use `docker compose -f compose.security.yaml up --build` for the supplied bounded
deployment, or apply equivalent hosting limits: 2 GiB memory, two CPUs, 128 PIDs,
two Gunicorn workers with four threads each, and one shared processing slot.
All replicas must use the same PostgreSQL database and DOCUMENT_MAX_JOBS value.
Changing workers alone does not establish container limits.

Document defaults are ceilings, configurable downward: 5 MiB signup input,
20 PDF pages, 14,400-point sides, 2,000-pixel render sides, four million pixels per
rendered page, 40 million total rendered pixels, 16 million decoded image pixels,
200,000 extracted characters, ten seconds per OCR call, 30 seconds per job, and
768 MiB per parser process. Linux uses resource limits and process-group cleanup;
Windows uses aggregate Job Object memory/CPU limits and descendant cleanup.
Job admission uses PostgreSQL advisory locks shared across web workers. A busy
extractor returns 503 promptly; parser deadline returns 422; invalid documents
return 400. Unavailable automatic extraction leaves manual signup entry usable.
Final signup document validation uses the same worker boundary.

Validate defaults against representative COR PDFs and faculty IDs in staging;
these samples and production delivery/resource access are not in the repository.
Check effective container limits with `docker inspect`, and load-test login and
browsing while submitting hostile documents. Never remove password confirmation
or restore in-process document parsing on rollback.

Abstract page requests serve stored abstracts. Populate missing abstracts outside
web requests with `python scripts/backfill_abstracts.py`; this bounds input to
20 MiB, PDFs to 200 pages, and text extraction to the first 20 pages with the same
memory/time/admission limits. Missing abstracts display an unavailable message.

Validation: 46 security tests passed; 54 supporting route/delivery checks passed.
Compose configuration validates. Container runtime checks remain unverified
because Docker's Linux daemon is unavailable. Two existing sample COR tests
cannot run successfully because their PDF fixture is missing. SMTP/SMS delivery,
representative document calibration, and production resource limits require staging.
