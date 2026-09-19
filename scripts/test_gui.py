"""Launch with: python scripts/test_gui.py"""
from collections import Counter
from datetime import datetime
from pathlib import Path
import queue
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.test_runner import TestRun, build_command, default_python, discover_tests
from scripts.test_gui_theme import apply_theme


class TestRunnerApp:
    def __init__(self, window):
        self.window = window
        window.title("CAPRE · Test Runner")
        window.geometry("1200x800")
        window.minsize(850, 600)
        self.run = None
        self.closing = False
        self.files = []
        self.results = {}
        self.rows = {}
        self.failures = []
        self.log = []
        self.completed = set()
        self.theme = "light"
        self.python = tk.StringVar(value=default_python())
        self.keyword = tk.StringVar()
        self.headed = tk.BooleanVar()
        self.show_prints = tk.BooleanVar()
        self.only_failures = tk.BooleanVar()
        self.status = tk.StringVar(value="Ready. Select files or run the entire suite.")
        self.counts = tk.StringVar(value="No tests run yet")
        self._build()
        apply_theme(self, self.theme)
        self.refresh_files()
        window.protocol("WM_DELETE_WINDOW", self.close)
        window.after(80, self.poll)

    def _build(self):
        style = ttk.Style(self.window)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        outer = ttk.Frame(self.window, padding=18, style="Page.TFrame")
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer, padding=(16, 10), style="Card.TFrame")
        header.pack(fill="x", pady=(0, 12))
        ttk.Label(header, text="CAPRE", style="Brand.TLabel").pack(side="left")
        ttk.Separator(header, orient="vertical").pack(side="left", fill="y", padx=16)
        ttk.Label(header, text="Development  /  Test Runner", style="Section.TLabel").pack(side="left")
        self.theme_button = ttk.Button(header, text="Dark mode", command=self.toggle_theme)
        self.theme_button.pack(side="right")
        configuration = ttk.Frame(outer, padding=14, style="Card.TFrame")
        configuration.pack(fill="x")
        ttk.Label(configuration, text="Test workspace", style="Title.TLabel").pack(anchor="w")
        ttk.Label(configuration, text="Run tests, inspect tracebacks, and rerun failures without a terminal.", style="Muted.TLabel").pack(anchor="w", pady=(2, 10))
        settings = ttk.Frame(configuration)
        settings.pack(fill="x")
        ttk.Label(settings, text="Python:").grid(row=0, column=0, sticky="w")
        self.python_entry = ttk.Entry(settings, textvariable=self.python)
        self.python_entry.grid(row=0, column=1, sticky="ew", padx=6)
        self.python_browse = ttk.Button(settings, text="Browse…", command=self.browse_python)
        self.python_browse.grid(row=0, column=2)
        ttk.Label(settings, text="Test filter (-k):").grid(row=1, column=0, sticky="w", pady=7)
        self.keyword_entry = ttk.Entry(settings, textvariable=self.keyword)
        self.keyword_entry.grid(row=1, column=1, sticky="ew", padx=6)
        settings.columnconfigure(1, weight=1)
        options = ttk.Frame(settings)
        options.grid(row=2, column=0, columnspan=3, sticky="w")
        self.headed_check = ttk.Checkbutton(options, text="Show browser windows", variable=self.headed)
        self.headed_check.pack(side="left")
        self.prints_check = ttk.Checkbutton(options, text="Stream test prints (-s)", variable=self.show_prints)
        self.prints_check.pack(side="left", padx=15)
        controls = ttk.Frame(outer, style="Page.TFrame")
        controls.pack(fill="x", pady=12)
        self.all_button = ttk.Button(controls, text="Run all tests", style="Accent.TButton", command=lambda: self.start_run(self.files))
        self.all_button.pack(side="left")
        self.selected_button = ttk.Button(controls, text="Run selected files", command=self.run_selected)
        self.selected_button.pack(side="left", padx=6)
        self.failed_button = ttk.Button(controls, text="Rerun failed", command=lambda: self.start_run(self.failures, rerun=True), state="disabled")
        self.failed_button.pack(side="left")
        self.stop_button = ttk.Button(controls, text="Stop after current test", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=6)
        self.force_button = ttk.Button(controls, text="Force stop", style="Danger.TButton", command=self.force_stop, state="disabled")
        self.force_button.pack(side="left")
        ttk.Button(controls, text="Save report…", command=self.save_report).pack(side="right")

        panes = ttk.Panedwindow(outer, orient="horizontal")
        panes.pack(fill="both", expand=True)
        left = ttk.Frame(panes, padding=12, style="Card.TFrame")
        panes.add(left, weight=1)
        self.file_label = ttk.Label(left, text="Test files", style="Section.TLabel")
        self.file_label.pack(anchor="w")
        file_frame = ttk.Frame(left)
        file_frame.pack(fill="both", expand=True, pady=5)
        self.file_list = tk.Listbox(file_frame, selectmode="extended", exportselection=False, width=32)
        self.file_list.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(file_frame, command=self.file_list.yview)
        scroll.pack(side="right", fill="y")
        self.file_list.configure(yscrollcommand=scroll.set)
        self.refresh_button = ttk.Button(left, text="Refresh files", command=self.refresh_files)
        self.refresh_button.pack(fill="x")
        ttk.Label(left, text="Ctrl / Shift: select multiple files\n\nBrowser tests need Playwright.\nDB tests need PostgreSQL tools.\nLocust and SQL scripts are not\npytest test files.", justify="left", style="Muted.TLabel").pack(anchor="w", pady=10)

        right = ttk.Frame(panes, padding=12, style="Card.TFrame")
        panes.add(right, weight=4)
        ttk.Label(right, text="Test results", style="Section.TLabel").pack(anchor="w")
        ttk.Label(right, textvariable=self.counts, style="Muted.TLabel").pack(anchor="w", pady=(3, 0))
        self.progress = ttk.Progressbar(right, mode="determinate")
        self.progress.pack(fill="x", pady=5)
        ttk.Checkbutton(right, text="Show failures only", variable=self.only_failures, command=self.filter_results).pack(anchor="w")
        vertical = ttk.Panedwindow(right, orient="vertical")
        vertical.pack(fill="both", expand=True)
        result_frame = ttk.Frame(vertical)
        vertical.add(result_frame, weight=3)
        self.tree = ttk.Treeview(result_frame, columns=("status", "time", "test"), show="headings", selectmode="browse")
        for column, title, width in (("status", "Status", 85), ("time", "Seconds", 65), ("test", "Test", 530)):
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, stretch=column == "test")
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical_scroll = ttk.Scrollbar(result_frame, orient="vertical", command=self.tree.yview)
        vertical_scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=vertical_scroll.set)
        scrollbar = ttk.Scrollbar(result_frame, orient="horizontal", command=self.tree.xview)
        scrollbar.grid(row=1, column=0, sticky="ew")
        self.tree.configure(xscrollcommand=scrollbar.set)
        result_frame.rowconfigure(0, weight=1)
        result_frame.columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self.show_details)
        notebook = ttk.Notebook(vertical)
        self.notebook = notebook
        vertical.add(notebook, weight=2)
        self.details = ScrolledText(notebook, wrap="word", font=("Consolas", 10), state="disabled", height=10)
        self.output = ScrolledText(notebook, wrap="word", font=("Consolas", 10), state="disabled", height=10)
        notebook.add(self.details, text="Selected test details")
        notebook.add(self.output, text="Live output")
        ttk.Button(right, text="Copy selected details", command=self.copy_details).pack(anchor="e", pady=(5, 0))
        ttk.Label(outer, textvariable=self.status, wraplength=1100, style="Status.TLabel").pack(anchor="w", pady=(8, 0))

    def toggle_theme(self):
        self.theme = "dark" if self.theme == "light" else "light"
        apply_theme(self, self.theme)

    @staticmethod
    def set_text(widget, text, append=False):
        widget.configure(state="normal")
        if not append:
            widget.delete("1.0", "end")
        widget.insert("end", text)
        if append:
            widget.see("end")
        widget.configure(state="disabled")

    def browse_python(self):
        path = filedialog.askopenfilename(title="Choose Python interpreter")
        if path:
            self.python.set(path)

    def refresh_files(self):
        self.files = discover_tests()
        self.file_list.delete(0, "end")
        for path in self.files:
            self.file_list.insert("end", path.removeprefix("tests/"))
        self.file_label.configure(text=f"Test files ({len(self.files)})")

    def run_selected(self):
        self.start_run([self.files[index] for index in self.file_list.curselection()])

    def set_busy(self, busy):
        for widget in (self.all_button, self.selected_button, self.refresh_button, self.python_entry,
                       self.python_browse, self.keyword_entry, self.headed_check, self.prints_check):
            widget.configure(state="disabled" if busy else "normal")
        self.failed_button.configure(state="normal" if self.failures and not busy else "disabled")
        self.stop_button.configure(state="normal" if busy else "disabled")
        self.force_button.configure(state="disabled")

    def start_run(self, targets, rerun=False):
        if self.run is not None:
            return
        targets = list(targets)
        if not targets:
            messagebox.showinfo("No tests selected", "Select at least one test file first.")
            return
        python = self.python.get().strip()
        if not Path(python).is_file():
            messagebox.showerror("Python not found", "Choose a Python executable. The project's venv is recommended.")
            return
        command = build_command(python, targets, "" if rerun else self.keyword.get(), self.headed.get(), self.show_prints.get())
        self.results.clear()
        for item in self.rows.values():
            self.tree.delete(item)
        self.rows.clear()
        self.completed.clear()
        self.failures = []
        self.log = [f"Started: {datetime.now().isoformat(timespec='seconds')}\n",
                    f"Folder: {ROOT}\n", f"Command: {subprocess.list2cmdline(command)}\n\n"]
        self.set_text(self.output, "".join(self.log))
        self.set_text(self.details, "Select a test to see its traceback and captured output.")
        self.counts.set("Collecting tests…")
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        self.status.set("Starting pytest…")
        self.set_busy(True)
        self.run = TestRun(command)
        self.run.start()

    def update_row(self, nodeid, **values):
        result = self.results.setdefault(nodeid, {"status": "pending", "duration": 0, "details": ""})
        result.update(values)
        row = self.rows.get(nodeid)
        if row is None:
            row = self.tree.insert("", "end")
            self.rows[nodeid] = row
        self.tree.item(row, values=(result["status"].upper(), f'{result["duration"]:.2f}', nodeid), tags=(result["status"],))
        if self.only_failures.get() and result["status"] not in ("failed", "error", "xpassed"):
            self.tree.detach(row)
        elif not self.tree.parent(row) and row not in self.tree.get_children():
            self.tree.move(row, "", "end")

    def filter_results(self):
        for nodeid in self.results:
            self.update_row(nodeid)

    def show_details(self, event=None):
        selection = self.tree.selection()
        if not selection:
            return
        nodeid = self.tree.item(selection[0], "values")[2]
        result = self.results[nodeid]
        self.set_text(self.details, f"{nodeid}\n{result['status'].upper()} · {result['duration']:.3f}s\n\n"
                      + (result["details"] or "No traceback or captured output."))

    def copy_details(self):
        self.window.clipboard_clear()
        self.window.clipboard_append(self.details.get("1.0", "end-1c"))

    def update_counts(self):
        counts = Counter(result["status"] for result in self.results.values())
        self.counts.set(f"{len(self.completed)}/{len(self.results)} complete  ·  " + "  ·  ".join(
            f"{status}: {counts[status]}" for status in ("passed", "failed", "error", "skipped", "xfailed", "xpassed") if counts[status]))
        self.progress.configure(value=len(self.completed), maximum=max(1, len(self.results)))

    def handle_event(self, event):
        kind = event["event"]
        if kind == "output":
            self.log.append(event["text"])
            self.set_text(self.output, event["text"], append=True)
        elif kind == "collected":
            self.progress.stop()
            self.progress.configure(mode="determinate")
            for nodeid in event["nodeids"]:
                self.update_row(nodeid)
            self.update_counts()
        elif kind == "started":
            self.update_row(event["nodeid"], status="running")
            self.status.set("Running: " + event["nodeid"])
        elif kind in ("result", "collection_error"):
            nodeid = event["nodeid"]
            self.update_row(nodeid, status=event.get("status", "error"), duration=event.get("duration", 0), details=event.get("details", ""))
            self.completed.add(nodeid)
            self.update_counts()
            if self.results[nodeid]["status"] in ("failed", "error") and not self.tree.selection():
                self.tree.selection_set(self.rows[nodeid])
                self.show_details()
            elif self.tree.selection() == (self.rows[nodeid],):
                self.show_details()
        elif kind in ("exited", "launch_error"):
            self.progress.stop()
            self.progress.configure(mode="determinate")
            for nodeid, result in self.results.items():
                if result["status"] in ("pending", "running"):
                    self.update_row(nodeid, status="not run" if result["status"] == "pending" else "interrupted")
            self.failures = [nodeid for nodeid, result in self.results.items() if result["status"] in ("failed", "error")]
            if kind == "launch_error":
                text = "Could not run tests: " + event["text"]
            elif event["stopped"]:
                text = "Stopped. Unfinished tests remain marked above."
            else:
                reasons = {0: "Tests passed", 1: "Tests failed", 2: "Interrupted or collection failed",
                           3: "Pytest internal error", 4: "Pytest command/configuration error", 5: "No tests matched"}
                text = reasons.get(event["exitcode"], "Test process ended") + f" (exit {event['exitcode']})."
                if not self.results and event["exitcode"] not in (0, 5):
                    text = f"Pytest could not start or collect tests (exit {event['exitcode']}). See Live output."
            if not self.results:
                self.notebook.select(self.output)
            self.status.set(text)
            self.log.append("\n" + text + "\n")
            self.set_text(self.output, "\n" + text + "\n", append=True)
            self.run = None
            self.set_busy(False)
            self.update_counts()
            if self.closing:
                self.window.destroy()

    def poll(self):
        if self.run is not None:
            # Bound each batch so large logs cannot starve Tk's event loop.
            active = self.run
            for _ in range(150):
                try:
                    event = active.events.get_nowait()
                except queue.Empty:
                    break
                self.handle_event(event)
                if self.run is None:
                    break
        if self.closing and self.run is None:
            return
        if self.window.winfo_exists():
            self.window.after(80, self.poll)

    def stop(self):
        if self.run is not None:
            self.run.stop()
            self.stop_button.configure(state="disabled")
            self.force_button.configure(state="normal")
            self.status.set("Stop requested. Waiting for current test and fixture cleanup…")

    def force_stop(self):
        if self.run is not None and messagebox.askyesno("Force stop?", "Kill this test process and its child processes? Fixture cleanup may not finish."):
            self.run.stop(force=True)
            self.force_button.configure(state="disabled")
            self.status.set("Stopping test processes…")

    def close(self):
        if self.run is None:
            self.window.destroy()
        elif messagebox.askyesno("Tests are running", "Stop after the current test and close when cleanup finishes?"):
            self.closing = True
            self.stop()

    def save_report(self):
        path = filedialog.asksaveasfilename(title="Save test report", defaultextension=".txt", initialfile="capre-test-report.txt", filetypes=[("Text report", "*.txt")])
        if not path:
            return
        sections = ["".join(self.log), "\n\nTEST RESULTS\n"]
        for nodeid, result in self.results.items():
            sections.append(f"\n{result['status'].upper()} {nodeid} ({result['duration']:.3f}s)\n{result['details']}\n")
        try:
            Path(path).write_text("".join(sections), encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Could not save report", str(exc))
        else:
            self.status.set("Report saved: " + path)


def main():
    window = tk.Tk()
    TestRunnerApp(window)
    window.mainloop()


if __name__ == "__main__":
    main()
