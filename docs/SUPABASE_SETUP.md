# CAPRE Supabase setup

Create a new **Free** project named `capre` in your Supabase organization.
Choose a region near your users, such as Singapore if available, and save the
database password in your password manager.

The setup below creates an empty cloud repository with lookup data. Existing
local accounts, capstones and files are not copied automatically.

## Connect the database

1. Open the project's **Connect** dialog and select **Session pooler**.
   Copy its host, port and username exactly. Session pooling supports IPv4
   connections from local development and hosted Flask services.
2. Copy `.env.supabase.example` to `.env.supabase` and fill in the PostgreSQL
   settings. `PG_PASSWORD` is the database password, not a Supabase API key.
   Keep `PG_SSLMODE=require`. Never commit `.env.supabase` or paste secrets in chat.
3. Run from the repository root:

   ```powershell
   venv\Scripts\python.exe scripts\setup_supabase.py
   ```

The script rejects projects with existing public tables, creates the final
schema, applies and records migrations, enables RLS, and creates private buckets
inside one transaction. Failure rolls back the setup. Use the ordinary migration
runner for future upgrades; do not rerun initialization on a populated project.

For the hosted Flask service, configure the same `PG_*` settings as environment
variables plus a fresh random `SECRET_KEY`. Configured pool size is per process;
start with `PG_POOL_MIN=1` and `PG_POOL_MAX=3`.

## Storage

The setup creates these private buckets:

| Bucket | Files | Maximum file size |
| --- | --- | --- |
| `capre-manuscripts` | PDF, DOC and DOCX | 25 MiB |
| `capre-registration` | COR PDFs | 5 MiB |
| `capre-avatars` | Sanitized PNG avatars | 2 MiB |

To enable cloud uploads, add the settings from `.env.storage.example` to your
active `.env` or hosted server environment. Set `UPLOAD_STORAGE_BACKEND=supabase`,
your project URL and a server-side secret key from Supabase's API Keys settings.
Use a new `sb_secret_...` key or a legacy `service_role` key, never a publishable key.
Restart Flask after saving the settings.

Manuscripts, COR documents and sanitized avatars then use private buckets. Flask
continues to authenticate users and authorize access. Files download server-side
into a temporary local cache for the existing PDF reader; browsers never receive
storage credentials or public file URLs. No additional Python package is required.

With `UPLOAD_STORAGE_BACKEND=local` (the default), uploads use local folders.
Existing local files are not transferred automatically when switching to Supabase.
Upload them again through the app or transfer them under their existing filenames
to the corresponding private buckets before switching existing records.

## Check the result

In Supabase, verify that the Table Editor contains the 20 application tables and
`schema_migration`, and Storage contains three private buckets. Role, program and
specialization lookups should be populated. No administrator account is created.

Before public deployment, test an upload and download for each file type, provision
your administrator account and configure the app's email provider.

References:
- [Database connections](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [Row level security](https://supabase.com/docs/guides/database/postgres/row-level-security)
- [Storage buckets](https://supabase.com/docs/guides/storage/buckets/creating-buckets)
