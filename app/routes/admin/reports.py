"""Admin reports routes and local helpers."""
from . import admin
from flask import jsonify, send_file
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
from app.utils.xlsx_export import build_specialization_workbook, build_table_workbook


@admin.route("/analytics/specialization/<int:specialization_id>/report")
@role_required(3)
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
@role_required(3)
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
@role_required(3)
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
@role_required(3)
def analytics_all_specializations_report():
    specializations, err = get_all_specialization_reports()
    if err:
        return jsonify({"success": False, "error": err}), 500

    return jsonify({
        "success": True,
        "specializations": specializations,
    })


@admin.route("/analytics/specializations/report.xlsx")
@role_required(3)
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
