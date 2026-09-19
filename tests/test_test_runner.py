"""Run tiny isolated suites to exercise the GUI's real subprocess protocol."""
import queue
import sys
import time

from scripts.test_runner import TestRun, build_command, default_python, discover_tests


def wait_for_run(run, timeout=25):
    run.thread.join(timeout)
    if run.thread.is_alive():
        run.stop(force=True)
        run.thread.join(10)
        raise AssertionError("Test runner did not finish")
    events = []
    while True:
        try:
            events.append(run.events.get_nowait())
        except queue.Empty:
            break
    return events


def test_discovery_includes_only_test_files(tmp_path):
    (tmp_path / "tests/nested").mkdir(parents=True)
    for name in ("test_one.py", "locustfile.py", "postgres_monitoring.sql", "nested/test_two.py"):
        (tmp_path / "tests" / name).touch()
    assert discover_tests(tmp_path) == ["tests/nested/test_two.py", "tests/test_one.py"]


def test_command_preserves_spaces_and_filter_as_arguments():
    command = build_command("C:/Python With Spaces/python.exe", ["tests/test_one.py::test_name"],
                            "profile and not browser", headed=True, show_prints=True)
    assert command[0] == "C:/Python With Spaces/python.exe"
    assert command[command.index("-k") + 1] == "profile and not browser"
    assert "--headed" in command and "-s" in command
    assert command[-1] == "tests/test_one.py::test_name"


def test_default_interpreter_exists():
    from pathlib import Path
    assert Path(default_python()).is_file()


def test_run_reports_pass_fail_skip_and_fixture_errors(tmp_path, monkeypatch):
    suite = tmp_path / "test_sample.py"
    suite.write_text('''import pytest
def test_pass():
    print("captured output")
def test_fail():
    assert False, "useful traceback"
@pytest.mark.skip(reason="not today")
def test_skip(): pass
@pytest.mark.xfail(reason="known issue")
def test_xfail(): assert False
@pytest.fixture
def bad_setup(): raise RuntimeError("setup broke")
def test_setup_error(bad_setup): pass
@pytest.fixture
def bad_teardown():
    yield
    raise RuntimeError("teardown broke")
def test_teardown_error(bad_teardown): pass
''', encoding="utf-8")
    # A developer's cached filter must not silently exclude selected GUI tests.
    monkeypatch.setenv("PYTEST_ADDOPTS", "-k nonexistent")
    run = TestRun(build_command(sys.executable, [str(suite)]))
    run.start()
    events = wait_for_run(run)
    results = {event["nodeid"].split("::")[-1]: event for event in events if event["event"] == "result"}
    assert {name: result["status"] for name, result in results.items()} == {
        "test_pass": "passed", "test_fail": "failed", "test_skip": "skipped", "test_xfail": "xfailed",
        "test_setup_error": "error", "test_teardown_error": "error",
    }
    assert "captured output" in results["test_pass"]["details"]
    assert "useful traceback" in results["test_fail"]["details"]
    assert "setup broke" in results["test_setup_error"]["details"]
    assert "teardown broke" in results["test_teardown_error"]["details"]
    assert events[-1]["event"] == "exited" and events[-1]["exitcode"] == 1
    assert any(event["event"] == "output" for event in events)


def test_collection_errors_are_visible(tmp_path):
    suite = tmp_path / "test_broken.py"
    suite.write_text('raise RuntimeError("cannot collect")\n', encoding="utf-8")
    run = TestRun(build_command(sys.executable, [str(suite)]))
    run.start()
    events = wait_for_run(run)
    assert any(event["event"] == "collection_error" and "cannot collect" in event["details"] for event in events)
    assert events[-1]["exitcode"] == 2


def test_missing_interpreter_reports_launch_error(tmp_path):
    run = TestRun([str(tmp_path / "missing-python")])
    run.start()
    events = wait_for_run(run)
    assert events[-1]["event"] == "launch_error"
    assert run.done.is_set()


def test_stop_finishes_current_test_and_runs_cleanup(tmp_path):
    suite = tmp_path / "test_stop.py"
    marker = tmp_path / "cleaned"
    suite.write_text(f'''import time
from pathlib import Path
import pytest
@pytest.fixture(scope="session")
def cleanup():
    yield
    Path({str(marker)!r}).touch()
def test_first(cleanup): time.sleep(0.6)
def test_second(): assert False, "must not run"
''', encoding="utf-8")
    run = TestRun(build_command(sys.executable, [str(suite)]))
    run.start()
    deadline = time.monotonic() + 20
    try:
        while time.monotonic() < deadline:
            event = run.events.get(timeout=10)
            if event["event"] == "started":
                run.stop()
                break
        else:
            raise AssertionError("No test started")
        events = wait_for_run(run)
    finally:
        if run.thread.is_alive():
            run.stop(force=True)
            run.thread.join(10)
    assert marker.exists()
    assert not any(event.get("nodeid", "").endswith("::test_second") and event["event"] == "result" for event in events)
    assert events[-1]["stopped"]


def test_force_stop_ends_owned_process():
    run = TestRun([sys.executable, "-u", "-c", "import time; print('ready', flush=True); time.sleep(30)"])
    run.start()
    try:
        event = run.events.get(timeout=10)
        assert event["event"] == "output" and "ready" in event["text"]
        run.stop(force=True)
        events = wait_for_run(run)
        assert events[-1]["event"] == "exited" and events[-1]["stopped"]
    finally:
        if run.thread.is_alive():
            run.stop(force=True)
            run.thread.join(10)
