"""Capstone Professor interfaces, separate from admin management routes."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for

from app.db.advisories import (
    add_advisory_students, get_advisory_groups,
    create_advisory_group_with_students, get_advisory_roster,
    get_available_advisory_students, remove_advisory_student,
    rename_advisory_group, MAX_ADVISORY_GROUP_STUDENTS,
)
from app.routes.decorators import role_required
from app.routes.forms import (
    AdvisoryGroupForm, AddAdvisoryStudentForm, CreateAdvisoryGroupForm,
    RemoveAdvisoryStudentForm,
)

faculty = Blueprint("faculty", __name__, url_prefix="/faculty")


def _add_student_form(groups=None, *, submitted=False):
    form = AddAdvisoryStudentForm() if submitted else AddAdvisoryStudentForm(formdata=None)
    groups = get_advisory_groups(session["user_id"]) if groups is None else groups
    form.group_id.choices = [(0, "Choose an advisory group")] + [
        (group["group_id"], f"{group['group_name']} ({group['student_count']}/{MAX_ADVISORY_GROUP_STUDENTS} students)")
        for group in groups if group["student_count"] < MAX_ADVISORY_GROUP_STUDENTS
    ]
    form.student_id.choices = [
        (student["user_id"], f"{student['full_name']} · {student['university_no'] or 'No university ID'} · Account #{student['user_id']}")
        for student in get_available_advisory_students(session["user_id"])
    ]
    return form


def _create_group_form(*, submitted=False):
    form = CreateAdvisoryGroupForm() if submitted else CreateAdvisoryGroupForm(formdata=None)
    form.student_ids.choices = [
        (student["user_id"], f"{student['full_name']} · {student['university_no'] or 'No university ID'} · Account #{student['user_id']}")
        for student in get_available_advisory_students(session["user_id"])
    ]
    return form


def _render_advisory_students(add_form=None, group_form=None, rename_form=None, rename_group_id=None):
    try:
        roster = get_advisory_roster(session["user_id"])
        groups = get_advisory_groups(session["user_id"])
        add_form = add_form or _add_student_form(groups)
        group_form = group_form or _create_group_form()
    except PermissionError:
        abort(403)
    search = request.args.get("search", "").strip()[:100]
    status = request.args.get("status", "")
    if status not in {"", "unregistered", "pending", "approved", "rejected"}:
        status = ""
    visible = [student for student in roster if
               (not status or student["capstoner_status"] == status) and
               (not search or search.casefold() in f"{student['full_name']} {student['university_no'] or ''} {student['user_id']}".casefold())]
    grouped = {group["group_id"]: dict(group, students=[], student_count=0) for group in groups}
    for student in roster:
        grouped[student["group_id"]]["student_count"] += 1
    for student in visible:
        grouped[student["group_id"]]["students"].append(student)
    visible_groups = [group for group in grouped.values() if group["students"] or not (search or status)]
    return render_template(
        "faculty/manage_capstone_users.html", professor=g.user, students=visible,
        groups=groups, visible_groups=visible_groups, group_limit=MAX_ADVISORY_GROUP_STUDENTS,
        group_spaces={str(group["group_id"]): max(0, MAX_ADVISORY_GROUP_STUDENTS - group["student_count"]) for group in groups},
        total_students=len(roster), search=search, selected_status=status,
        metrics=[
            {"label": "Students", "value": len(roster)},
            {"label": "Approved capstoners", "value": sum(s["capstoner_status"] == "approved" for s in roster)},
            {"label": "Pending registrations", "value": sum(s["capstoner_status"] == "pending" for s in roster)},
            {"label": "With linked works", "value": sum(bool(s["works"]) for s in roster)},
        ],
        group_form=group_form or AdvisoryGroupForm(formdata=None),
        rename_form=rename_form, rename_group_id=rename_group_id,
        add_form=add_form, remove_form=RemoveAdvisoryStudentForm(formdata=None),
    )


@faculty.route("/advisory-students")
@role_required(4)
def manage_capstone_users():
    return _render_advisory_students()


@faculty.route("/advisory-students/groups", methods=["POST"])
@role_required(4)
def create_group():
    try:
        form = _create_group_form(submitted=True)
    except PermissionError:
        abort(403)
    if not form.validate_on_submit():
        flash("Enter a group name between 1 and 100 characters.", "danger")
        return _render_advisory_students(group_form=form), 400
    if form.student_ids.data and not form.confirmed.data:
        form.confirmed.errors.append("Confirm that you are assigned to advise all selected students.")
        flash("Confirm that you are assigned to advise all selected students.", "danger")
        return _render_advisory_students(group_form=form), 400
    ok, error = create_advisory_group_with_students(
        session["user_id"], form.group_name.data, form.student_ids.data or []
    )
    count = len(form.student_ids.data or [])
    message = f"Group created with {count} {'student' if count == 1 else 'students'}." if count else "Group created."
    flash(message if ok else error, "success" if ok else "danger")
    if not ok:
        return _render_advisory_students(group_form=form), 400
    return redirect(url_for("faculty.manage_capstone_users", _anchor="add-advisory-student"))


@faculty.route("/advisory-students/groups/<int:group_id>/rename", methods=["POST"])
@role_required(4)
def rename_group(group_id):
    form = AdvisoryGroupForm()
    if not form.validate_on_submit():
        flash("Enter a group name between 1 and 100 characters.", "danger")
        return _render_advisory_students(rename_form=form, rename_group_id=group_id), 400
    ok, error = rename_advisory_group(session["user_id"], group_id, form.group_name.data)
    flash("Group renamed. Its students and author credits are unchanged." if ok else error,
          "success" if ok else "danger")
    if not ok:
        return _render_advisory_students(rename_form=form, rename_group_id=group_id), 400
    return redirect(url_for("faculty.manage_capstone_users", _anchor=f"advisory-group-{group_id}"))


@faculty.route("/advisory-students/add", methods=["POST"])
@role_required(4)
def add_student():
    try:
        form = _add_student_form(submitted=True)
    except PermissionError:
        abort(403)
    if not form.validate_on_submit():
        flash(f"Choose a group with space (maximum {MAX_ADVISORY_GROUP_STUDENTS} students) and available students, then confirm your adviser relationship.", "danger")
        return _render_advisory_students(form), 400
    ok, error = add_advisory_students(session["user_id"], form.student_id.data, form.group_id.data)
    count = len(form.student_id.data)
    flash(f"{count} {'student' if count == 1 else 'students'} added to your advisory roster. Capstoner status and author credits are unchanged." if ok else error,
          "success" if ok else "danger")
    if not ok:
        return _render_advisory_students(form), 400
    return redirect(url_for("faculty.manage_capstone_users"))


@faculty.route("/advisory-students/<int:student_id>/remove", methods=["POST"])
@role_required(4)
def remove_student(student_id):
    form = RemoveAdvisoryStudentForm()
    if not form.validate_on_submit():
        flash("Confirm that you want to remove the student from your roster.", "danger")
        return _render_advisory_students(), 400
    ok, error = remove_advisory_student(session["user_id"], student_id)
    flash("Student removed from your roster only. Their account and capstones are unchanged." if ok else error,
          "success" if ok else "danger")
    if not ok:
        return _render_advisory_students(), 400
    return redirect(url_for("faculty.manage_capstone_users"))
