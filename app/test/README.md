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

## Advisory students (experimental)

After the two migrations above, apply `migrations/20260908_advisory_students.sql`,
then `migrations/20260908_advisory_groups.sql` to the experimental database.
If the roster migration is already applied, only run the new groups migration.
Existing roster memberships are preserved in an **Existing advisory students**
group for each professor, which can be renamed. Professors without students get
no automatic group, and existing accounts are not enrolled automatically.

1. Sign in as an active **Capstone Professor** and open **Management → Advisory
   Students**. The outer paper/binder container is removed to use the available
   width; group sections retain the system's dashed lines, paper colors and theme.
2. **Create a group** first. Blank names and names over 100 characters are
   rejected; duplicate names within your roster are rejected ignoring case and
   surrounding spaces. Another professor may use the same name.
3. Select your **Advisory group** and a verified **Student** account, check its university ID/account number,
   confirm that you advise the student, then add them. Same-name accounts remain
   separate. Adding a student does not approve capstoner registration or link works.
   A student belongs to one group per professor. The server also rejects additions
   without a group or using another professor's group ID.
   Each group has a **maximum of 4 students**. Counts show `0 / 4` through `4 / 4`;
   full groups are excluded from the add selector. Try a fifth addition, including
   from a stale tab: it must fail. Simultaneous adds cannot take the same last place.
   Remove a student to reopen a place, or create another group. Existing groups
   above four keep their students and show **Over limit**; remove enough students
   to get below four before adding again. No new migration is needed for this limit.
4. Expand **Rename group**, edit the name, then save. The heading and group selector
   update; memberships, capstoner approvals and author links stay unchanged.
   Search your roster by name, university ID or account number; filter by
   capstoner status. Overview totals always describe the full roster.
5. Approve a registration/link an author credit through the existing **Capstoner
   Review** page, then return: the status and non-archived linked works update.
   Approving a registration does not automatically add the student to a roster.
6. A second professor sees only their own groups and cannot rename yours. Co-advisers may add the same
   student independently; no student is transferred between rosters.
7. Expand a student's works and roster options. Confirm removal: only your
   membership is removed, not the student's account, approval, author links or
   other professors' memberships. Re-add to restore membership. Changes are audited.
8. Student, Faculty and Admin accounts cannot manage rosters. No activity tracking,
   student notification, manuscript-access grant or capstone adviser credit is
   created by membership. Test light/dark mode and narrow phone widths.

```powershell
python -m pytest app/test/test_advisory_students.py -q
```

These tests also use isolated temporary PostgreSQL, not the application database.

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
