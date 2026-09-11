# Original-branch feature setup

1. Back up the original branch database and confirm the app points to it, not the experimental database.
2. Run `20260910_verification_documents.sql` on that database before restarting the app. It adds only `user.cor_filename`; fresh databases from `capreDB.sql` already have the column.
3. Sign up using a readable COR PDF (maximum 5 MB and 20 pages). Sign in as Admin, open **Users & Roles → Verify Accounts → View details / COR**, and download the PDF before deciding.
4. Check **Audit Logs** and **Title Similarity**. Neither needs additional tables. The `/propose-topic` URL is preserved.

The app reads `UPLOAD_MANUSCRIPT_FOLDER` and `UPLOAD_REGISTRATION_FOLDER` from `.env`. COR files go into the registration folder with unique filenames; only the filename is stored on the user. Failed signups clean up their new files. Keep both folders writable by the app and back them up alongside the database. Legacy manuscript locations remain readable.

The current settings put these folders under `app/static/uploads`. Flask blocks public `/static/uploads/` requests; configure any front-end web server to block that path too (do not serve it directly). Admins download COR PDFs through the protected verification route. Validation is not a malware scan. Files are retained after review or request deletion; account/file retention cleanup is not automatic. Older accounts without a COR remain reviewable.

The migration is additive and does not drop any old document table. If an earlier version stored real COR bytes in that table on another database, export them to the registration folder and populate `user.cor_filename` before switching; retain a backup until checked. No live database migration or file relocation is run automatically.
