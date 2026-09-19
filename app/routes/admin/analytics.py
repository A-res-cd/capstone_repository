"""Admin analytics routes."""
from . import admin
from flask import render_template, flash, jsonify, send_file
from werkzeug.utils import secure_filename
from app.db.analytics import (
    get_capstones_by_specialization,
    get_capstones_by_program,
    get_capstone_trend_by_specialization,
    get_capstone_status_flags,
    get_all_specialization_reports,
    get_specialization_report,
)
from app.routes.decorators import role_required
from app.constants.roles import ROLE_ADMIN
from app.utils.xlsx_export import build_specialization_workbook, build_table_workbook


@admin.route("/analytics")
@role_required(ROLE_ADMIN)
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


@admin.route("/analytics/specialization/<int:specialization_id>/report")
@role_required(ROLE_ADMIN)
def analytics_specialization_report(specialization_id):
    rows, specialization, err = get_specialization_report(specialization_id)
    if err:
        return jsonify({"success": False, "error": err}), 500
    if specialization is None:
        return jsonify({"success": False, "error": "Specialization not found."}), 404

    return jsonify({
        "success": True,
        "specialization": specialization,
        "records": rows,
    })


@admin.route("/analytics/specialization/<int:specialization_id>/report.xlsx")
@role_required(ROLE_ADMIN)
def analytics_specialization_workbook(specialization_id):
    rows, specialization, err = get_specialization_report(specialization_id)
    if err:
        return jsonify({"success": False, "error": err}), 500
    if specialization is None:
        return jsonify({"success": False, "error": "Specialization not found."}), 404

    workbook = build_specialization_workbook([{
        "specialization_id": specialization_id,
        "specialization_name": specialization,
        "records": rows,
    }])
    filename = secure_filename(specialization).lower() or "specialization"
    return send_file(
        workbook,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"capre-{filename}-capstones.xlsx",
    )


@admin.route("/analytics/report.xlsx")
@role_required(ROLE_ADMIN)
def analytics_workbook():
    by_specialization, specialization_err = get_capstones_by_specialization()
    by_program, program_err = get_capstones_by_program()
    trend_years, trend_series, trend_err = get_capstone_trend_by_specialization()
    status_flags, status_err = get_capstone_status_flags()
    if any((specialization_err, program_err, trend_err, status_err)):
        return jsonify({
            "success": False,
            "error": "Analytics data is temporarily unavailable.",
        }), 500

    total = sum(row["total"] for row in by_program)
    status_flags = status_flags or {}

    def share(value, whole=total):
        return f"{((value / whole) * 100) if whole else 0:.1f}%"

    status_groups = (
        ("Publication", (("Published", total), ("Not Published", 0))),
        ("Utilization", (("Utilized", status_flags.get("utilized", 0)),
                         ("Not Utilized", status_flags.get("not_utilized", 0)))),
        ("Presentation", (("Presented", status_flags.get("presented", 0)),
                          ("Not Presented", status_flags.get("not_presented", 0)))),
        ("Copyright", (("Registered", status_flags.get("copyright_registered", 0)),
                       ("Not Registered", status_flags.get("not_copyright_registered", 0)))),
    )
    status_rows = [
        (metric, label, value, share(value))
        for metric, values in status_groups
        for label, value in values
    ]
    trend_names = list(trend_series)
    tables = [
        {
            "title": "Overview",
            "headers": ("Metric", "Value"),
            "rows": (("Total Capstones", total),),
            "widths": (32, 18),
        },
        {
            "title": "Programs",
            "headers": ("Program", "Capstones", "Share of Total"),
            "rows": tuple(
                (row["program_name"], row["total"], share(row["total"]))
                for row in by_program
            ),
            "widths": (30, 15, 18),
        },
        {
            "title": "Status",
            "headers": ("Metric", "Status", "Count", "Share"),
            "rows": tuple(status_rows),
            "widths": (20, 24, 14, 14),
        },
        {
            "title": "Yearly Trend",
            "headers": ("Year", *trend_names),
            "rows": tuple(
                (year, *(trend_series[name][index] for name in trend_names))
                for index, year in enumerate(trend_years)
            ),
            "widths": (12, *(16 for _ in trend_names)),
        },
        {
            "title": "Specializations",
            "headers": ("Specialization", "Capstones", "Share of Total"),
            "rows": tuple(
                (row["specialization_name"], row["total"], share(row["total"]))
                for row in by_specialization
            ),
            "widths": (28, 15, 18),
        },
        {
            "title": "Summary",
            "headers": ("Specialization", "Total Capstone", "Published", "Utilized",
                        "Presented", "Copyright Registered"),
            "rows": tuple(
                (
                    row["specialization_name"],
                    f'{row["total"]} ({share(row["total"])})',
                    f'{row["total"]} ({share(row["total"], row["total"])})',
                    f'{row["utilized"]} ({share(row["utilized"], row["total"])})',
                    f'{row["presented"]} ({share(row["presented"], row["total"])})',
                    f'{row["copyright_registered"]} '
                    f'({share(row["copyright_registered"], row["total"])})',
                )
                for row in by_specialization
            ),
            "widths": (28, 18, 18, 18, 18, 25),
        },
    ]
    return send_file(
        build_table_workbook(tables),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="capre-analytics-report.xlsx",
    )


@admin.route("/analytics/specializations/report")
@role_required(ROLE_ADMIN)
def analytics_all_specializations_report():
    specializations, err = get_all_specialization_reports()
    if err:
        return jsonify({"success": False, "error": err}), 500

    return jsonify({
        "success": True,
        "specializations": specializations,
    })


@admin.route("/analytics/specializations/report.xlsx")
@role_required(ROLE_ADMIN)
def analytics_all_specializations_workbook():
    specializations, err = get_all_specialization_reports()
    if err:
        return jsonify({"success": False, "error": err}), 500

    return send_file(
        build_specialization_workbook(specializations),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="capre-all-specializations.xlsx",
    )
