"""Initialize a new empty Supabase project, atomically, from CAPRE's final schema."""

import argparse
from pathlib import Path
import sys

from dotenv import load_dotenv
import psycopg2

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def initialize(conn):
    from app.db.migration_runner import (
        MIGRATION_TABLE_SQL, _migration_sql, migration_checksum, migration_files,
    )

    try:
        with conn.cursor() as cursor:
            cursor.execute("SET LOCAL search_path TO public")
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext('capre.schema-migrations'))")
            cursor.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                )
            """)
            if cursor.fetchone()[0]:
                raise RuntimeError('Project already has tables. Use a new empty CAPRE project.')
            cursor.execute((ROOT / 'database/capre_original_final.sql').read_text(encoding='utf-8'))
            cursor.execute(MIGRATION_TABLE_SQL)
            # Final schema folds in column changes; replay migrations for indexes
            # and store checksums so future upgrades do not repeat old migrations.
            for path in migration_files():
                cursor.execute(_migration_sql(path))
                cursor.execute(
                    'INSERT INTO schema_migration (migration_name, checksum) VALUES (%s, %s)',
                    (path.name, migration_checksum(path)),
                )
            cursor.execute((ROOT / 'database/supabase_setup.sql').read_text(encoding='utf-8'))
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', default='.env.supabase')
    args = parser.parse_args(argv)
    env_path = Path(args.env_file)
    if not env_path.is_file():
        print('Copy .env.supabase.example to .env.supabase and fill in project settings.', file=sys.stderr)
        return 1
    load_dotenv(env_path, override=True)

    conn = None
    try:
        from config import Config
        if not Config.PG_HOST.endswith(('.supabase.co', '.pooler.supabase.com')):
            raise RuntimeError('PG_HOST must be the Supabase project or session pooler host.')
        conn = psycopg2.connect(
            host=Config.PG_HOST, port=Config.PG_PORT, user=Config.PG_USER,
            password=Config.PG_PASSWORD, database=Config.PG_DB,
            sslmode='require', connect_timeout=10,
        )
        initialize(conn)
        print('CAPRE schema, migrations, lookup data and three private buckets created.')
        return 0
    except Exception as exc:
        # Do not print connection errors containing hostnames or credential details.
        print(f'Supabase setup failed ({type(exc).__name__}). No setup changes committed.', file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            conn.close()


if __name__ == '__main__':
    raise SystemExit(main())
