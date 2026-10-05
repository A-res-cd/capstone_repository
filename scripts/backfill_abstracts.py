"""Cache abstracts from existing PDFs without exposing manuscript contents."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask
from config import Config
from app.db.connection import db_connect
from app.utils.uploads import resolve_manuscript_file
from app.utils.pdf_extractor import extract_abstract_text


def main():
    root = Path(__file__).resolve().parents[1]
    app = Flask('abstract_backfill', root_path=str(root / 'app'), instance_path=str(root / 'instance'))
    app.config.from_object(Config)
    import os
    app.config['UPLOAD_MANUSCRIPT_FOLDER'] = os.environ.get('UPLOAD_MANUSCRIPT_FOLDER')
    updated = skipped = 0
    conn = db_connect()
    try:
        with app.app_context(), conn.cursor() as cursor:
            cursor.execute('SELECT capstone_id, capstone_file FROM capstone WHERE abstract_text IS NULL')
            for capstone_id, filename in cursor.fetchall():
                path = resolve_manuscript_file(filename)
                if not path or Path(path).suffix.lower() != '.pdf':
                    skipped += 1
                    continue
                abstract = extract_abstract_text(path)
                cursor.execute('UPDATE capstone SET abstract_text = %s WHERE capstone_id = %s AND abstract_text IS NULL', (abstract, capstone_id))
                updated += cursor.rowcount
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    print(f'Abstracts processed: {updated}; unavailable/non-PDF manuscripts: {skipped}')


if __name__ == '__main__':
    main()
