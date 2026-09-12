from io import BytesIO
from types import SimpleNamespace

from flask import Flask
import pytest
from werkzeug.datastructures import FileStorage

from app.utils import malware_scan
from app.utils import upload_cleanup
from app.utils.uploads import save_manuscript_upload, validate_manuscript_upload


def upload(filename, content):
    return FileStorage(stream=BytesIO(content), filename=filename)


def test_manuscript_validation_checks_extension_and_signature():
    app = Flask(__name__)
    with app.app_context():
        assert validate_manuscript_upload(upload("paper.pdf", b"%PDF-1.7")) is None
        assert validate_manuscript_upload(upload("paper.pdf", b"not a pdf"))
        assert validate_manuscript_upload(upload("paper.txt", b"%PDF-1.7"))
        assert validate_manuscript_upload(upload("paper.docx", b"PK\x03\x04")) is None


def test_manuscript_validation_applies_configured_size_limit():
    app = Flask(__name__)
    app.config["UPLOAD_MANUSCRIPT_MAX_BYTES"] = 4
    with app.app_context():
        assert validate_manuscript_upload(upload("paper.pdf", b"%PDF-1.7"))


def test_required_scanner_rejects_when_not_configured():
    app = Flask(__name__)
    app.config["UPLOAD_ANTIVIRUS_REQUIRED"] = True
    with app.app_context():
        with pytest.raises(malware_scan.UploadScanError):
            malware_scan.scan_uploaded_file("paper.pdf")


def test_scanner_uses_no_shell_and_rejects_infected_file(monkeypatch, tmp_path):
    app = Flask(__name__)
    app.config["UPLOAD_ANTIVIRUS_COMMAND"] = "scanner"
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(malware_scan.subprocess, "run", run)
    with app.app_context():
        assert malware_scan.scan_uploaded_file(tmp_path / "paper.pdf")
    assert calls[0][0] == ["scanner", str(tmp_path / "paper.pdf")]
    assert calls[0][1]["shell"] is False

    def infected(command, **kwargs):
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(malware_scan.subprocess, "run", infected)
    with app.app_context():
        with pytest.raises(malware_scan.UploadScanError, match="malware"):
            malware_scan.scan_uploaded_file(tmp_path / "paper.pdf")


def test_required_scanner_removes_manuscript_after_rejection(tmp_path):
    app = Flask(__name__)
    app.config["UPLOAD_MANUSCRIPT_FOLDER"] = str(tmp_path)
    app.config["UPLOAD_ANTIVIRUS_REQUIRED"] = True
    with app.app_context():
        filename, error = save_manuscript_upload(upload("paper.pdf", b"%PDF-1.7"))

    assert filename is None
    assert "scanning" in error
    assert list(tmp_path.iterdir()) == []


class InventoryCursor:
    def execute(self, query, params=None):
        pass

    def fetchall(self):
        return [("uploads/kept.pdf",)]

    def close(self):
        pass


class InventoryConnection:
    def __init__(self):
        self.cursor_value = InventoryCursor()

    def cursor(self):
        return self.cursor_value

    def rollback(self):
        pass

    def close(self):
        pass


def test_orphan_report_is_read_only_and_keeps_referenced_files(monkeypatch, tmp_path):
    app = Flask(__name__)
    app.config["UPLOAD_ORPHAN_RETENTION_DAYS"] = 1
    folder = tmp_path / "uploads"
    folder.mkdir()
    kept = folder / "kept.pdf"
    orphan = folder / "orphan.pdf"
    kept.write_bytes(b"kept")
    orphan.write_bytes(b"orphan")

    monkeypatch.setattr(upload_cleanup, "db_connect", InventoryConnection)
    monkeypatch.setattr(upload_cleanup, "manuscript_upload_folder", lambda: str(folder))
    monkeypatch.setattr(upload_cleanup, "registration_upload_folder", lambda: folder)
    monkeypatch.setattr(upload_cleanup, "avatar_upload_folder", lambda: folder)
    old_timestamp = orphan.stat().st_mtime - (3 * 24 * 60 * 60)
    import os
    os.utime(orphan, (old_timestamp, old_timestamp))

    with app.app_context():
        report = upload_cleanup.find_orphaned_uploads()

    assert [entry["path"] for entry in report] == [str(orphan)]
    assert kept.exists() and orphan.exists()


def test_cleanup_deletes_only_old_orphaned_files(monkeypatch, tmp_path):
    app = Flask(__name__)
    app.config["UPLOAD_ORPHAN_RETENTION_DAYS"] = 1
    folder = tmp_path / "uploads"
    folder.mkdir()
    kept = folder / "kept.pdf"
    orphan = folder / "orphan.pdf"
    kept.write_bytes(b"kept")
    orphan.write_bytes(b"orphan")

    monkeypatch.setattr(upload_cleanup, "db_connect", InventoryConnection)
    monkeypatch.setattr(upload_cleanup, "manuscript_upload_folder", lambda: str(folder))
    monkeypatch.setattr(upload_cleanup, "registration_upload_folder", lambda: folder)
    monkeypatch.setattr(upload_cleanup, "avatar_upload_folder", lambda: folder)
    old_timestamp = orphan.stat().st_mtime - (3 * 24 * 60 * 60)
    import os
    os.utime(orphan, (old_timestamp, old_timestamp))

    with app.app_context():
        assert upload_cleanup.delete_orphaned_uploads() == 1

    assert kept.exists() and not orphan.exists()


def test_cleanup_fails_closed_when_database_references_are_unavailable(monkeypatch, tmp_path):
    app = Flask(__name__)
    app.config["UPLOAD_ORPHAN_RETENTION_DAYS"] = 1
    folder = tmp_path / "uploads"
    folder.mkdir()
    orphan = folder / "orphan.pdf"
    orphan.write_bytes(b"orphan")
    monkeypatch.setattr(upload_cleanup, "_referenced_upload_names", lambda: None)
    monkeypatch.setattr(upload_cleanup, "manuscript_upload_folder", lambda: str(folder))
    monkeypatch.setattr(upload_cleanup, "registration_upload_folder", lambda: folder)
    monkeypatch.setattr(upload_cleanup, "avatar_upload_folder", lambda: folder)

    with app.app_context():
        assert upload_cleanup.delete_orphaned_uploads() == 0

    assert orphan.exists()
