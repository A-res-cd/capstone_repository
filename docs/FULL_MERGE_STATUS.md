# Full branch merge

Merge inputs: `aresVer` at `a64ab6d`, preview at `5bee0f4`, and
`aresver-css` at `45378b8`. The completed merge is advanced onto `aresVer`.

Conflict resolution retains RET Chair/System Administrator separation, author
account links, capstoner review, advisory/progress, saved capstones, promotion
requests, activity tracking, system administration and migration checksum checks.
The saved-capstone retirement migration is excluded because this merged version
retains the saved-capstone workflow.

Incoming account contact/terms/password handling, role-change password checks,
request purposes, analytics/year/publication reporting, styling, and the
authentication/manuscript/report module split are included. Incoming academic
Admin checks use RET Chair. Original manuscript downloads use the incoming
restriction, mapped to RET Chair; approved users keep the watermarked reader.

Merge checks: Python files compile, route modules import, and all six blueprints
register without duplicate endpoints. The route map has 105 entries, including
the retained feature routes and incoming picture/history/reader/report routes.
Application debugging and the full regression suite are deferred to the next
step. The earlier preview's test results describe the preview, not this full merge.

The configured application database has not been migrated or seeded. Review and
test the combined migrations before applying them. Backup branch refs retain
both the original `aresVer` and the preview. The local role-seeder update remains
ignored by Git, as configured in `.gitignore`.
