"""Adapt the web application's shared design tokens to native Tk widgets."""
from pathlib import Path
import re
from tkinter import font, ttk

TOKENS_FILE = Path(__file__).resolve().parents[1] / "app/static/css/base/root.css"


def web_palette(mode="light"):
    source = re.sub(r"/\*.*?\*/", "", TOKENS_FILE.read_text(encoding="utf-8"), flags=re.S)
    selectors = [":root"]
    if mode == "dark":
        selectors.append('[data-theme="dark"]')
    values = {}
    for selector in selectors:
        block = re.search(re.escape(selector) + r"\s*\{([^}]+)\}", source)
        values.update(re.findall(r"--([\w-]+)\s*:\s*([^;]+);", block.group(1)))

    def resolve(name, seen=()):
        if name in seen:
            raise ValueError(f"Circular CSS token: {name}")
        value = values[name].strip()
        return re.sub(r"var\(--([\w-]+)\)", lambda match: resolve(match[1], (*seen, name)), value)

    return {name: resolve(name) for name in values}


def apply_theme(app, mode):
    colors = web_palette(mode)
    app.palette = colors
    page, paper, ink = (colors[key] for key in ("surface-page", "surface-paper", "text-dark"))
    brand, border = colors["text-brand"], colors["border-color"]
    muted, field = colors["text-placeholder"], colors["surface-input"]
    families = set(font.families(app.window))
    heading_font = "Fraunces" if "Fraunces" in families else "Segoe UI"
    style = ttk.Style(app.window)
    style.theme_use("clam")
    app.window.configure(background=page)
    style.configure(".", font=("Segoe UI", 10), background=paper, foreground=ink,
                    bordercolor=border, lightcolor=border, darkcolor=border, troughcolor=page)
    style.configure("TFrame", background=paper)
    style.configure("Page.TFrame", background=page)
    style.configure("Card.TFrame", background=paper, borderwidth=1, relief="solid")
    style.configure("TLabel", background=paper, foreground=ink)
    style.configure("Brand.TLabel", foreground=brand, font=("Segoe UI", 19, "bold"))
    style.configure("Title.TLabel", foreground=brand, font=(heading_font, 16, "bold"))
    style.configure("Section.TLabel", foreground=brand, font=("Segoe UI", 10, "bold"))
    style.configure("Muted.TLabel", foreground=muted)
    style.configure("Status.TLabel", background=page, foreground=muted, font=("Segoe UI", 9))
    style.configure("TSeparator", background=border)
    style.configure("TPanedwindow", background=page, sashwidth=8)
    style.configure("TButton", foreground=brand, background=paper, padding=(10, 7),
                    borderwidth=1, focusthickness=1, focuscolor=brand)
    style.map("TButton", background=[("disabled", colors["surface-muted"]), ("pressed", colors["surface-selected"]), ("active", colors["hover-tint"])],
              foreground=[("disabled", muted)], bordercolor=[("focus", brand), ("active", colors["color-primary-soft"])])
    style.configure("Accent.TButton", background=colors["color-accent"], foreground=colors["text-on-accent"],
                    bordercolor=colors["color-accent"], font=("Segoe UI", 10, "bold"))
    style.map("Accent.TButton", background=[("disabled", colors["surface-muted"]), ("pressed", colors["color-accent-hover"]), ("active", colors["color-accent-hover"])],
              foreground=[("disabled", muted), ("!disabled", colors["text-on-accent"])])
    style.configure("Danger.TButton", foreground=colors["status-rejected"])
    style.map("Danger.TButton", background=[("disabled", colors["surface-muted"]), ("active", colors["surface-danger"])])
    style.configure("TEntry", fieldbackground=field, foreground=ink, insertcolor=ink,
                    padding=7, bordercolor=colors["border-input"])
    style.map("TEntry", fieldbackground=[("disabled", colors["surface-muted"])],
              foreground=[("disabled", muted)], bordercolor=[("focus", brand)],
              selectbackground=[("!disabled", colors["color-primary"])], selectforeground=[("!disabled", colors["color-white"])])
    style.configure("TCheckbutton", background=paper, foreground=ink, padding=(0, 4),
                    indicatorbackground=field, indicatorforeground=colors["color-white"], indicatorcolor=field)
    style.map("TCheckbutton", background=[("active", paper)], foreground=[("disabled", muted)],
              indicatorbackground=[("selected", colors["color-primary"]), ("active", colors["hover-tint"])])
    style.configure("Treeview", background=colors["bg-card-neutral"], fieldbackground=colors["bg-card-neutral"],
                    foreground=ink, rowheight=29, borderwidth=0)
    style.map("Treeview", background=[("selected", colors["surface-selected"])], foreground=[("selected", colors["text-brand-strong"])])
    style.configure("Treeview.Heading", background=colors["bg-card-header"], foreground=brand,
                    font=("Segoe UI", 10, "bold"), padding=(8, 8), relief="flat")
    style.map("Treeview.Heading", background=[("active", colors["hover-tint"])])
    style.configure("TNotebook", background=paper, borderwidth=0)
    style.configure("TNotebook.Tab", background=colors["surface-muted"], foreground=muted, padding=(14, 8))
    style.map("TNotebook.Tab", background=[("selected", colors["bg-card-neutral"]), ("active", colors["hover-tint"])],
              foreground=[("selected", brand), ("active", brand)])
    style.configure("Horizontal.TProgressbar", background=colors["color-accent"], troughcolor=colors["surface-muted"],
                    bordercolor=border, lightcolor=colors["color-accent"], darkcolor=colors["color-accent"], thickness=6)
    for orientation in ("Vertical", "Horizontal"):
        style.configure(f"{orientation}.TScrollbar", background=colors["border-input"], troughcolor=paper,
                        arrowcolor=brand, borderwidth=0, arrowsize=12)
        style.map(f"{orientation}.TScrollbar", background=[("active", colors["color-primary-soft"])])
    app.file_list.configure(background=paper, foreground=ink, font=("Segoe UI", 10), borderwidth=0,
                            highlightthickness=1, highlightbackground=border, highlightcolor=brand,
                            selectbackground=colors["surface-selected"], selectforeground=colors["text-brand-strong"],
                            activestyle="none", selectborderwidth=0)
    for widget in (app.details, app.output):
        widget.configure(background=colors["bg-card-neutral"], foreground=ink, insertbackground=ink,
                         selectbackground=colors["color-primary"], selectforeground=colors["color-white"],
                         borderwidth=0, highlightthickness=1, highlightbackground=border,
                         highlightcolor=brand, padx=12, pady=10)
        widget.vbar.configure(background=colors["border-input"], troughcolor=paper,
                              activebackground=colors["color-primary-soft"], highlightthickness=0, borderwidth=0)
    for status, token in {"passed": "status-approved", "failed": "status-rejected", "error": "status-rejected",
                          "running": "text-brand", "skipped": "status-pending", "xfailed": "status-pending",
                          "xpassed": "status-pending", "pending": "text-placeholder",
                          "not run": "status-cancelled", "interrupted": "status-cancelled"}.items():
        app.tree.tag_configure(status, foreground=colors[token])
    app.theme_button.configure(text="Light mode" if mode == "dark" else "Dark mode")
