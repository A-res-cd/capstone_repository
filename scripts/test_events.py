"""Pytest event adapter for the desktop test runner."""
import json
import os
from pathlib import Path

import pytest


def summarize_reports(reports):
    """Combine setup/call/teardown without counting a test more than once."""
    status = "passed"
    details = []
    for report in reports:
        if report.failed:
            candidate = "failed" if report.when == "call" else "error"
        elif report.skipped:
            candidate = "xfailed" if hasattr(report, "wasxfail") else "skipped"
        elif hasattr(report, "wasxfail"):
            candidate = "xpassed"
        else:
            candidate = "passed"
        priority = {"passed": 0, "xpassed": 1, "xfailed": 2, "skipped": 3, "failed": 4, "error": 5}
        if priority[candidate] > priority[status]:
            status = candidate
        if report.longrepr:
            details.append(f"{report.when.upper()}\n{report.longreprtext}")
        for title, content in report.sections:
            section = f"{title}\n{content}"
            if section not in details:
                details.append(section)
    return {
        "status": status,
        "duration": sum(report.duration for report in reports),
        "details": "\n\n".join(details),
    }


class EventReporter:
    def __init__(self, event_file, stop_file):
        self.event_file = event_file
        self.stop_file = Path(stop_file)
        self.reports = {}

    def emit(self, event, **values):
        self.event_file.write(json.dumps({"event": event, **values}, ensure_ascii=True) + "\n")
        self.event_file.flush()

    def pytest_collection_finish(self, session):
        self.emit("collected", nodeids=[item.nodeid for item in session.items])

    def pytest_collectreport(self, report):
        if report.failed:
            self.emit("collection_error", nodeid=report.nodeid, details=report.longreprtext)

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_protocol(self, item, nextitem):
        if self.stop_file.exists():
            pytest.exit("Stopped from the test runner", returncode=2)

    def pytest_runtest_logstart(self, nodeid, location):
        self.emit("started", nodeid=nodeid)

    def pytest_runtest_logreport(self, report):
        reports = self.reports.setdefault(report.nodeid, [])
        reports.append(report)
        if report.when == "teardown":
            self.emit("result", nodeid=report.nodeid, **summarize_reports(reports))
            del self.reports[report.nodeid]

    def pytest_sessionfinish(self, session, exitstatus):
        self.emit("session_finished", exitcode=int(exitstatus))


def pytest_configure(config):
    event_path = os.environ.get("CAPRE_TEST_EVENTS")
    if not event_path:
        return
    stream = open(event_path, "a", encoding="utf-8", buffering=1)
    config.add_cleanup(stream.close)
    config.pluginmanager.register(EventReporter(stream, os.environ["CAPRE_TEST_STOP"]), "capre-gui-events")
