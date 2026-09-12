from pathlib import Path

from app.db.migration_runner import _migration_sql, migration_checksum, migration_files


def test_migration_files_are_sql_only_and_sorted(tmp_path):
    (tmp_path / "20260902_later.sql").write_text("SELECT 2;", encoding="utf-8")
    (tmp_path / "20260901_first.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "notes.md").write_text("not SQL", encoding="utf-8")

    assert [path.name for path in migration_files(tmp_path)] == [
        "20260901_first.sql",
        "20260902_later.sql",
    ]


def test_migration_sql_removes_only_outer_transaction_markers(tmp_path):
    path = tmp_path / "sample.sql"
    path.write_text(
        "BEGIN;\nALTER TABLE example ADD COLUMN value INT;\n"
        "DO $$\nBEGIN\n  NULL;\nEND $$;\nCOMMIT;\n",
        encoding="utf-8",
    )

    sql = _migration_sql(path)
    assert not sql.startswith("BEGIN;")
    assert not sql.endswith("COMMIT;")
    assert "DO $$\nBEGIN\n  NULL;" in sql


def test_migration_checksum_is_stable(tmp_path):
    path = Path(tmp_path / "sample.sql")
    path.write_text("SELECT 1;", encoding="utf-8")

    assert migration_checksum(path) == migration_checksum(path)
    assert len(migration_checksum(path)) == 64
