from types import SimpleNamespace

import pytest

from scripts import verify_backup


def test_verify_backup_checks_archive_without_database_access(tmp_path, monkeypatch):
    backup = tmp_path / "capre.dump"
    backup.write_bytes(b"custom-format-placeholder")
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="TABLE public.user\n", stderr="")

    monkeypatch.setattr(verify_backup.shutil, "which", lambda command: "pg_restore.exe")
    assert verify_backup.verify_backup(backup, runner=run) == "TABLE public.user\n"
    assert calls == [(
        ["pg_restore.exe", "--list", "--exit-on-error", str(backup)],
        {"capture_output": True, "text": True},
    )]


def test_verify_backup_rejects_missing_archive(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        verify_backup.verify_backup(tmp_path / "missing.dump")
