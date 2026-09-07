"""Author identity regressions; PostgreSQL runs in an isolated temporary cluster."""
from importlib import import_module
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import uuid

from flask import Flask, g
import psycopg2
import pytest
from werkzeug.datastructures import MultiDict
from wtforms.validators import ValidationError

from app.db import capstones
from app.routes.forms import AuthorForm, UpdateCapstoneForm

ROOT = Path(__file__).resolve().parents[2]
admin_routes = import_module("app.routes.admin")


@pytest.fixture(scope="module")
def author_postgres(tmp_path_factory):
    initdb, pg_ctl = shutil.which("initdb"), shutil.which("pg_ctl")
    if not initdb or not pg_ctl:
        pytest.skip("PostgreSQL initdb and pg_ctl are required for isolated database tests")
    cluster = tmp_path_factory.mktemp("author-links-postgres")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    def run(*args):
        # postgres inherits startup handles on Windows; a PIPE can keep
        # communicate() waiting even after pg_ctl successfully exits.
        with tempfile.TemporaryFile() as output:
            result = subprocess.run(
                args, stdout=output, stderr=subprocess.STDOUT,
                timeout=45, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            output.seek(0)
            assert result.returncode == 0, output.read().decode(errors="replace")

    run(initdb, "-D", str(cluster), "-A", "trust", "-U", "postgres", "--encoding=UTF8", "--no-locale")
    run(pg_ctl, "-D", str(cluster), "-l", str(cluster / "server.log"),
        "-o", f"-h 127.0.0.1 -p {port} -F", "-w", "start")
    try:
        yield {"host": "127.0.0.1", "port": port, "user": "postgres", "dbname": "postgres"}
    finally:
        run(pg_ctl, "-D", str(cluster), "-m", "fast", "-w", "stop")


@pytest.fixture
def author_db(author_postgres, monkeypatch):
    schema = "author_test_" + uuid.uuid4().hex
    setup = psycopg2.connect(**author_postgres)
    setup.autocommit = True
    with setup.cursor() as cursor:
        cursor.execute(f'CREATE SCHEMA "{schema}"')
    setup.close()

    def connect():
        return psycopg2.connect(**author_postgres, options=f"-c search_path={schema}")

    with connect() as conn, conn.cursor() as cursor:
        cursor.execute((ROOT / "capreDB.sql").read_text(encoding="utf-8").split("CREATE DATABASE capre;", 1)[1])
        cursor.execute('''
            INSERT INTO role (role_id, role_name) VALUES
                (1, 'Student'), (2, 'Faculty'), (3, 'Admin'), (4, 'Capstone Professor');
            INSERT INTO "user" (user_id, user_first_name, user_last_name, role_id, account_status)
                VALUES (1, 'Maria', 'Cruz', 1, 'active'), (2, 'Maria', 'Cruz', 1, 'active');
            INSERT INTO request (user_id, request_type, request_status)
                VALUES (1, 'capstoner', 'approved'), (2, 'capstoner', 'approved');
            INSERT INTO capstone (capstone_id, capstone_title, capstone_year, is_archived)
                VALUES (1, 'Linked Work', 2026, false), (2, 'Unlinked Work', 2025, false),
                       (3, 'Archived Work', 2024, true), (4, 'Adviser Only', 2026, false);
        ''')
    conn.close()
    monkeypatch.setattr(capstones, "db_connect", connect)
    return connect


def people_payload(capstone_id):
    rows = capstones.get_capstone_people(capstone_id)
    people = [{"author_id": row["author_id"], "user_id": row["user_id"],
               "first": row["aut_first_name"], "middle": row["aut_middle_name"],
               "last": row["aut_last_name"], "role": row["role"]} for row in rows]
    return [p for p in people if p["role"] == "Author"], next(p for p in people if p["role"] == "Adviser")


ADVISER = {"first": "Jane", "last": "Adviser"}
AUTHOR = {"first": "Maria", "last": "Cruz", "user_id": 1}


def test_coauthors_same_names_unlinked_archived_and_adviser_credits(author_db):
    assert capstones.set_capstone_people(1, [AUTHOR, dict(AUTHOR, user_id=2)], ADVISER)[0]
    assert capstones.set_capstone_people(2, [dict(AUTHOR, user_id=None)], ADVISER)[0]
    assert capstones.set_capstone_people(3, [AUTHOR], ADVISER)[0]
    assert capstones.set_capstone_people(4, [], ADVISER)[0]
    with author_db() as conn, conn.cursor() as cursor:
        cursor.execute("UPDATE author SET user_id = 1 WHERE author_id IN (SELECT author_id FROM capauth WHERE capstone_id = 4)")
    conn.close()
    for user_id in (1, 2):
        assert [work["capstone_id"] for work in capstones.get_user_authored_capstones(user_id)] == [1]
    assert capstones.get_user_authored_capstones(99) == []
    assert len(capstones.get_author_account_choices()) == 2


def test_edit_keeps_ids_links_and_order_then_explicitly_unlinks(author_db):
    assert capstones.set_capstone_people(1, [AUTHOR, dict(AUTHOR, user_id=2)], ADVISER)[0]
    before = capstones.get_capstone_people(1)
    authors, adviser = people_payload(1)
    authors.reverse()
    authors[0]["first"] = "Mariana"
    assert capstones.set_capstone_people(1, authors, adviser)[0]
    after = capstones.get_capstone_people(1)
    assert [p["author_id"] for p in after] == [before[1]["author_id"], before[0]["author_id"], before[2]["author_id"]]
    assert [p["user_id"] for p in after] == [2, 1, None]
    authors[1].pop("user_id")  # Omitted by a legacy caller means preserve, not unlink.
    assert capstones.set_capstone_people(1, authors, adviser)[0]
    assert capstones.get_user_authored_capstones(1)
    authors[1]["user_id"] = None
    assert capstones.set_capstone_people(1, authors, adviser)[0]
    assert capstones.get_user_authored_capstones(1) == []
    assert len(capstones.get_user_authored_capstones(2)) == 1


def test_invalid_links_and_tampered_author_ids_roll_back(author_db):
    assert capstones.set_capstone_people(1, [AUTHOR], ADVISER)[0]
    assert capstones.set_capstone_people(2, [dict(AUTHOR, user_id=2)], ADVISER)[0]
    before = capstones.get_capstone_people(1)
    authors, adviser = people_payload(1)
    foreign_authors, _ = people_payload(2)
    for invalid_authors in (
        authors + [dict(AUTHOR)],
        [dict(authors[0], user_id=99)],
        foreign_authors,
        [dict(authors[0], first="", last="")],
        [dict(authors[0], author_id=adviser["author_id"])],
        authors + authors,
    ):
        ok, error = capstones.set_capstone_people(1, invalid_authors, adviser)
        assert not ok and error
        assert capstones.get_capstone_people(1) == before


def test_shared_legacy_credit_changes_only_selected_capstone(author_db):
    assert capstones.set_capstone_people(1, [AUTHOR], ADVISER)[0]
    authors, adviser = people_payload(1)
    old_id = authors[0]["author_id"]
    with author_db() as conn, conn.cursor() as cursor:
        cursor.execute("INSERT INTO capauth VALUES (2, %s, 'Author', 1)", (old_id,))
    conn.close()
    assert capstones.set_capstone_people(1, authors, adviser)[0]
    assert people_payload(1)[0][0]["author_id"] == old_id
    authors[0]["first"] = "Mariana"
    assert capstones.set_capstone_people(1, authors, adviser)[0]
    assert people_payload(1)[0][0]["author_id"] != old_id
    assert capstones.get_capstone_people(2)[0]["user_id"] == 1
    assert capstones.get_capstone_people(2)[0]["aut_first_name"] == "Maria"
    assert [w["capstone_id"] for w in capstones.get_user_authored_capstones(1)] == [1, 2]


def test_migration_is_repeatable_and_deleted_account_keeps_credit(author_db):
    with author_db() as conn, conn.cursor() as cursor:
        cursor.execute("ALTER TABLE author DROP COLUMN user_id")
        cursor.execute("INSERT INTO author (aut_first_name, aut_last_name) VALUES ('Old', 'Author')")
        migration = (ROOT / "migrations/20260907_author_account_links.sql").read_text(encoding="utf-8")
        cursor.execute(migration)
        cursor.execute(migration)
        cursor.execute("SELECT user_id FROM author")
        assert cursor.fetchall() == [(None,)]
    conn.close()
    assert capstones.set_capstone_people(1, [AUTHOR], ADVISER)[0]
    before = capstones.get_capstone_people(1)
    with author_db() as conn, conn.cursor() as cursor:
        cursor.execute('DELETE FROM request WHERE user_id = 1')
        cursor.execute('DELETE FROM "user" WHERE user_id = 1')
    conn.close()
    after = capstones.get_capstone_people(1)
    assert after[0]["author_id"] == before[0]["author_id"]
    assert after[0]["aut_first_name"] == "Maria"
    assert after[0]["user_id"] is None


def test_author_form_rejects_unknown_accounts_and_duplicate_links():
    app = Flask(__name__)
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_request_context():
        form = AuthorForm(MultiDict({"user_id": "99", "first_name": "Maria"}))
        form.user_id.choices = [(0, "No linked account"), (1, "Maria Cruz")]
        assert not form.validate()
        assert form.user_id.errors
        form = UpdateCapstoneForm(MultiDict({
            "authors-0-user_id": "1", "authors-0-first_name": "Maria",
            "authors-1-user_id": "1", "authors-1-first_name": "Maria",
        }))
        with pytest.raises(ValidationError, match="only one author"):
            form.validate_authors(form.authors)


def test_people_endpoint_returns_failure_without_exposing_database_error(monkeypatch):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "author-links-test"
    app.register_blueprint(admin_routes.admin)

    @app.before_request
    def load_admin():
        g.user = {"role_id": 3}

    def fail(_):
        raise RuntimeError("private database detail")

    monkeypatch.setattr(admin_routes, "get_capstone_people", fail)
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = 1
        response = client.get("/repository/1/people")
    assert response.status_code == 503
    assert response.json == {"success": False, "error": "Could not load author links."}
