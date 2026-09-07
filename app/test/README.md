# CAPRE Testing Setup

## Capstoner registration and author links (experimental)

Run these migrations against the experimental database, in order:

1. `migrations/20260907_author_account_links.sql`
2. `migrations/20260907_capstoner_registration.sql`

Existing authors stay unlinked. No accounts are automatically registered as
capstoners. Do not rerun the full `capreDB.sql` against an existing database.

1. As an active user, open **Profile Overview → Register as Capstoner** and
   provide capstone details. The profile should show **Pending**; a second
   pending request must be blocked. Users who are not authors need not apply.
2. As a **Capstone Professor**, open **Capstoner Review**. Reject with feedback
   and check that the user can reapply. Then approve: the user's role and login
   verification must stay unchanged, and My Works must remain empty until linked.
   Decisions appear in the user's existing notification bell and profile.
3. On **Capstoner Review → Link an author credit**, choose an account and the
   exact unlinked credit, confirm authorship, then submit. This can also approve
   an unregistered, pending, or previously rejected capstoner directly. The linked capstone should now
   appear only in that account's **My Works**. Same-name users are not matched.
4. Self-approval/assignment, duplicate credits, and overwriting another account's
   link must fail. Admin/Faculty/Student accounts cannot use professor review.
5. Repository linking now accepts only approved capstoners for new links.
   Edit/reorder the authors and save again: links must remain attached to the
   same people. Same-name accounts are distinguished by account number.
6. Choose **No linked account**: the credit remains, but leaves that user's
   My Works. Other coauthors keep their work. Archived works stay hidden.
   Capstoner approval remains separate from the list of linked works.
7. View/citation/manuscript-request activity alerts are not enabled yet;
   the profile shows placeholders instead of sample activity counts.

Run focused checks from the repository root:

```powershell
python -m pytest app/test/test_capstoner_registration.py app/test/test_author_account_links.py app/test/test_user_capstones.py app/test/test_repository_author_links_ui.py -q
```

Database tests start/stop their own temporary PostgreSQL cluster on a random
loopback port; they never use the configured application database. Put
`initdb` and `pg_ctl` on PATH to run them (otherwise they skip).

## Install
```
pip install -r requirements.txt
playwright install
```

## 1. Load testing (Locust)
```
locust -f locustfile.py --host=http://localhost:5000
```
Open http://localhost:8089 → set number of users + spawn rate → start.
Edit selectors/payloads in `locustfile.py` to match your actual `auth`,
`main`, `admin` blueprint routes and form field names.

## 2. E2E browser testing (Playwright)
```
pytest test_e2e_workflow.py --headed
```
Update CSS selectors in `test_e2e_workflow.py` to match your Jinja
templates (login form, archive result cards, error messages).

## 3. Database monitoring
While Locust runs, open `postgres_monitoring.sql` in psql/pgAdmin and
run each query to check active connections, slow queries, and cache
hit ratio.

## 4. Multi-device / multi-network testing
Expose your local Flask server via VS Code Dev Tunnel, then hit that
URL from real phones/laptops on Wi-Fi and mobile data to verify IP
logging and responsiveness.

## 5. API testing
Import your `/signin`, `/signup`, `/request`, `/archive` routes into
Postman or Bruno for endpoint-level correctness checks (separate from
Locust's load testing).
