"""Widget behavior checks; no application tests or database are launched."""
import queue

import pytest

tk = pytest.importorskip("tkinter")
from scripts import test_gui


@pytest.fixture(scope="module")
def tk_root():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def ui(tk_root):
    window = tk.Toplevel(tk_root)
    window.withdraw()
    app = test_gui.TestRunnerApp(window)
    yield app
    try:
        if window.winfo_exists():
            window.destroy()
    except tk.TclError:
        pass


def test_failure_details_filter_and_counts(ui):
    ui.handle_event({"event": "collected", "nodeids": ["tests/a.py::good", "tests/a.py::bad"]})
    ui.handle_event({"event": "result", "nodeid": "tests/a.py::good", "status": "passed", "duration": 0.2})
    ui.handle_event({"event": "started", "nodeid": "tests/a.py::bad"})
    ui.handle_event({"event": "result", "nodeid": "tests/a.py::bad", "status": "failed", "duration": 0.3,
                     "details": "AssertionError: useful failure"})
    assert "2/2 complete" in ui.counts.get()
    assert "useful failure" in ui.details.get("1.0", "end")
    ui.only_failures.set(True)
    ui.filter_results()
    assert ui.tree.get_children() == (ui.rows["tests/a.py::bad"],)
    ui.only_failures.set(False)
    ui.filter_results()
    assert len(ui.tree.get_children()) == 2


def test_failed_rerun_uses_nodeids_and_clears_old_keyword(ui, monkeypatch):
    class FakeRun:
        def __init__(self, command):
            self.command = command
            self.events = queue.Queue()

        def start(self):
            pass

    monkeypatch.setattr(test_gui, "TestRun", FakeRun)
    ui.handle_event({"event": "result", "nodeid": "tests/a.py::bad", "status": "failed"})
    ui.handle_event({"event": "exited", "exitcode": 1, "stopped": False})
    assert ui.failures == ["tests/a.py::bad"]
    ui.keyword.set("old filter")
    ui.start_run(ui.failures, rerun=True)
    assert ui.run.command[-1] == "tests/a.py::bad"
    assert "-k" not in ui.run.command
    assert not ui.results
    assert "disabled" in ui.all_button.state()


def test_process_error_unlocks_controls_and_keeps_message(ui):
    ui.set_busy(True)
    ui.handle_event({"event": "launch_error", "text": "pytest is unavailable"})
    assert "pytest is unavailable" in ui.status.get()
    assert "pytest is unavailable" in ui.output.get("1.0", "end")
    assert "disabled" not in ui.all_button.state()
    assert ui.notebook.select() == str(ui.output)


def test_missing_pytest_directs_user_to_output(ui):
    ui.handle_event({"event": "output", "text": "No module named pytest\n"})
    ui.handle_event({"event": "exited", "exitcode": 1, "stopped": False})
    assert "could not start or collect" in ui.status.get()
    assert ui.notebook.select() == str(ui.output)


def test_save_report_includes_details(ui, monkeypatch, tmp_path):
    path = tmp_path / "report.txt"
    monkeypatch.setattr(test_gui.filedialog, "asksaveasfilename", lambda **kwargs: str(path))
    ui.handle_event({"event": "output", "text": "Live test log\n"})
    ui.handle_event({"event": "result", "nodeid": "tests/a.py::bad", "status": "error", "details": "Fixture failed"})
    ui.save_report()
    text = path.read_text(encoding="utf-8")
    assert "Live test log" in text and "Fixture failed" in text and "tests/a.py::bad" in text


def test_close_waits_for_worker_without_scheduling_on_destroyed_window(ui, monkeypatch):
    class FakeRun:
        def __init__(self):
            self.events = queue.Queue()
            self.stopped = False

        def stop(self):
            self.stopped = True

    active = FakeRun()
    ui.run = active
    monkeypatch.setattr(test_gui.messagebox, "askyesno", lambda *args: True)
    ui.close()
    assert ui.closing and active.stopped
    active.events.put({"event": "exited", "exitcode": 2, "stopped": True})
    ui.poll()
    assert ui.run is None
