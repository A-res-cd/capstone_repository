"""Admin analytics routes and local helpers."""
from . import admin
from flask import render_template, flash
from app.db.analytics import (
    get_capstones_by_specialization,
    get_capstones_by_program,
    get_capstone_trend_by_specialization,
    get_capstone_status_flags,
)
from app.routes.decorators import role_required


@admin.route("/analytics")
@role_required(3)
def analytics():
    db_errors = []

    by_specialization, err = get_capstones_by_specialization()
    if err:
        db_errors.append(f"Capstones by specialization: {err}")

    by_program, err = get_capstones_by_program()
    if err:
        db_errors.append(f"Capstones by program: {err}")

    trend_years, trend_series, err = get_capstone_trend_by_specialization()
    if err:
        db_errors.append(f"Capstone trend by specialization: {err}")

    status_flags, err = get_capstone_status_flags()
    if err:
        db_errors.append(f"Capstone status flags: {err}")

    if db_errors:
        for msg in db_errors:
            flash(f"Analytics query failed — {msg}", "danger")

    specialization_labels = [row["specialization_name"] for row in by_specialization]
    specialization_totals = [row["total"] for row in by_specialization]

    program_labels = [row["program_name"] for row in by_program]
    program_totals = [row["total"] for row in by_program]

    # ── Summary card figures ──
    total_capstones = sum(program_totals)

    # ── Published / Utilized / Presented / Copyright Registered donuts.
    # Every archived-in record is inherently "published" (no draft
    # workflow state exists), so Published is always total/total. ──
    status_flags = status_flags or {}
    published_labels = ["Published", "Not Published"]
    published_totals = [total_capstones, 0]

    utilized_labels = ["Utilized", "Not Utilized"]
    utilized_totals = [status_flags.get("utilized", 0), status_flags.get("not_utilized", 0)]

    presented_labels = ["Presented", "Not Presented"]
    presented_totals = [status_flags.get("presented", 0), status_flags.get("not_presented", 0)]

    copyright_labels = ["Registered", "Not Registered"]
    copyright_totals = [status_flags.get("copyright_registered", 0), status_flags.get("not_copyright_registered", 0)]

    # ── Per-program stat cards, in the reference dashboard's style ──
    program_cards = []
    for row in by_program:
        pct = round((row["total"] / total_capstones) * 100, 1) if total_capstones else 0
        program_cards.append({
            "name": row["program_name"],
            "total": row["total"],
            "pct": pct,
        })

    # ── Summary-by-specialization table rows, with per-metric percentages ──
    def _pct(part, whole):
        return round((part / whole) * 100, 1) if whole else 0

    summary_rows = []
    for row in (by_specialization or []):
        total = row["total"]
        summary_rows.append({
            "id": row["specialization_id"],
            "name": row["specialization_name"],
            "total": total,
            "total_pct": _pct(total, total_capstones),
            "published": total,
            "published_pct": _pct(total, total),
            "utilized": row["utilized"],
            "utilized_pct": _pct(row["utilized"], total),
            "presented": row["presented"],
            "presented_pct": _pct(row["presented"], total),
            "copyright_registered": row["copyright_registered"],
            "copyright_pct": _pct(row["copyright_registered"], total),
        })

    summary_totals = {
        "total": total_capstones,
        "published": total_capstones,
        "utilized": sum(r["utilized"] for r in summary_rows),
        "presented": sum(r["presented"] for r in summary_rows),
        "copyright_registered": sum(r["copyright_registered"] for r in summary_rows),
    }

    return render_template(
        "admin/analytics.html",
        specialization_labels=specialization_labels,
        specialization_totals=specialization_totals,
        program_labels=program_labels,
        program_totals=program_totals,
        program_cards=program_cards,
        trend_years=trend_years,
        trend_series=trend_series,
        has_db_errors=bool(db_errors),
        total_capstones=total_capstones,
        published_labels=published_labels,
        published_totals=published_totals,
        utilized_labels=utilized_labels,
        utilized_totals=utilized_totals,
        presented_labels=presented_labels,
        presented_totals=presented_totals,
        copyright_labels=copyright_labels,
        copyright_totals=copyright_totals,
        summary_rows=summary_rows,
        summary_totals=summary_totals,
    )
