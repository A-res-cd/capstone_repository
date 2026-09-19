"""Admin capstoners routes."""
from . import admin
from flask import render_template, redirect, session, url_for, flash
from app.routes.decorators import role_required
from app.constants.roles import ROLE_ADMIN, ROLE_CAPSTONE_PROFESSOR
from app.routes.forms import CapstonerReviewForm, CapstonerAssignmentForm
from app.db.capstoners import (
    get_pending_capstoners,
    review_capstoner_registration,
    get_capstoner_assignment_choices,
    assign_capstoner_credit,
)
from .repository import _first_form_error


def _capstoner_assignment_form():
    form = CapstonerAssignmentForm()
    accounts, credits = get_capstoner_assignment_choices()
    form.user_id.choices = [(0, "Choose an account")]
    for account in accounts:
        if account["user_id"] != session["user_id"]:
            label = f"{account['full_name']} · {account['university_no'] or 'No university ID'} · Account #{account['user_id']}"
            form.user_id.choices.append((account["user_id"], label, {"data-account-name": account["full_name"]}))
    form.credit.choices = [("", "Choose an unlinked author credit")] + [
        (f"{credit['capstone_id']}:{credit['author_id']}",
         f"{credit['author_name']} — {credit['capstone_title']} ({credit['capstone_year']}) · Credit #{credit['author_id']}",
         {"data-author-name": credit["author_name"]})
        for credit in credits
    ]
    return form


def _render_capstoner_review(assignment_form=None):
    return render_template(
        "admin/capstoners.html", pending_capstoners=get_pending_capstoners(),
        review_form=CapstonerReviewForm(),
        assignment_form=assignment_form or _capstoner_assignment_form(),
    )


@admin.route("/capstoners")
@role_required(ROLE_ADMIN, ROLE_CAPSTONE_PROFESSOR)
def capstoner_review():
    return _render_capstoner_review()


@admin.route("/capstoners/review/<int:request_id>", methods=["POST"])
@role_required(ROLE_ADMIN, ROLE_CAPSTONE_PROFESSOR)
def decide_capstoner(request_id):
    form = CapstonerReviewForm()
    if not form.validate_on_submit():
        flash(_first_form_error(form), "danger")
        return _render_capstoner_review(), 400
    ok, error = review_capstoner_registration(request_id, form.decision.data, form.status_reason.data, session["user_id"])
    flash("Capstoner request reviewed. No capstone was linked automatically." if ok else error, "success" if ok else "danger")
    if not ok:
        return _render_capstoner_review(), 400
    return redirect(url_for("admin.capstoner_review"))


@admin.route("/capstoners/assign", methods=["POST"])
@role_required(ROLE_ADMIN, ROLE_CAPSTONE_PROFESSOR)
def assign_capstoner():
    form = _capstoner_assignment_form()
    if not form.validate_on_submit():
        flash(_first_form_error(form), "danger")
        return _render_capstoner_review(form), 400
    capstone_id, author_id = (int(value) for value in form.credit.data.split(":"))
    ok, error = assign_capstoner_credit(capstone_id, author_id, form.user_id.data, session["user_id"])
    flash("Author credit linked. The user is an approved capstoner." if ok else error, "success" if ok else "danger")
    if not ok:
        return _render_capstoner_review(form), 400
    return redirect(url_for("admin.capstoner_review"))
