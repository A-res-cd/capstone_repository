"""Subprocess management shared by the Tk UI and its regression tests."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]


def discover_tests(root=ROOT):
    return sorted(path.relative_to(root).as_posix() for path in (root / "tests").rglob("test_*.py"))


def default_python(root=ROOT):
    for folder in ("venv", ".venv"):
        candidate = root / folder / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if candidate.is_file():
            return str(candidate)
    return sys.executable


def build_command(python, targets, keyword="", headed=False, show_prints=False):
    command = [python, "-u", "-m", "pytest", "-p", "scripts.test_events", "-v", "--tb=short", "--color=no"]
    if keyword.strip():
        command.extend(["-k", keyword.strip()])
    if headed:
        command.append("--headed")
    if show_prints:
        command.append("-s")
    return command + list(targets)


class TestRun:
    """Stream output and JSON events without blocking Tk or touching its widgets."""
    __test__ = False

    def __init__(self, command, root=ROOT):
        self.command = command
        self.root = root
        self.events = queue.Queue()
        self.process = None
        self.stopping = threading.Event()
        self.force_requested = threading.Event()
        self.done = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self, force=False):
        self.stopping.set()
        if force:
            self.force_requested.set()

    def _force_stop(self):
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(self.process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW, check=False, timeout=10,
            )
        else:
            import signal
            os.killpg(self.process.pid, signal.SIGKILL)

    def _output(self):
        for line in self.process.stdout:
            self.events.put({"event": "output", "text": line})
        self.process.stdout.close()

    def _run(self):
        output_thread = None
        try:
            with tempfile.TemporaryDirectory(prefix="capre-tests-") as folder:
                event_path = Path(folder) / "events.jsonl"
                stop_path = Path(folder) / "stop"
                event_path.touch()
                environment = os.environ.copy()
                environment.update(CAPRE_TEST_EVENTS=str(event_path), CAPRE_TEST_STOP=str(stop_path),
                                   PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
                environment["PYTHONPATH"] = str(self.root) + os.pathsep + environment.get("PYTHONPATH", "")
                # Cached developer pytest flags must not silently restrict a GUI run.
                environment.pop("PYTEST_ADDOPTS", None)
                options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
                self.process = subprocess.Popen(
                    self.command, cwd=self.root, env=environment, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", **options,
                )
                output_thread = threading.Thread(target=self._output, daemon=True)
                output_thread.start()
                pending = ""
                forced = False
                with event_path.open(encoding="utf-8") as stream:
                    while True:
                        if self.stopping.is_set():
                            stop_path.touch(exist_ok=True)
                        if self.force_requested.is_set() and not forced and self.process.poll() is None:
                            self._force_stop()
                            forced = True
                        finished = self.process.poll() is not None
                        pending += stream.read()
                        while "\n" in pending:
                            line, pending = pending.split("\n", 1)
                            try:
                                self.events.put(json.loads(line))
                            except ValueError:
                                self.events.put({"event": "output", "text": "Could not read test event: " + line + "\n"})
                        if finished:
                            break
                        time.sleep(0.05)
                output_thread.join(timeout=2)
                self.events.put({"event": "exited", "exitcode": self.process.returncode,
                                 "stopped": self.stopping.is_set()})
        except Exception as exc:
            if self.process is not None and self.process.poll() is None:
                try:
                    self._force_stop()
                    self.process.wait(timeout=10)
                except Exception as cleanup_error:
                    self.events.put({"event": "output", "text": f"Process cleanup failed: {cleanup_error}\n"})
            self.events.put({"event": "launch_error", "text": str(exc)})
        finally:
            self.done.set()
