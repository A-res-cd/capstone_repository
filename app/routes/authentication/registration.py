"""Authentication registration routes and local helpers."""
from . import auth
from flask import flash, render_template, request, redirect, url_for, jsonify
import logging
from app.db.auth import create_user
from app.utils.cor_upload import save_cor_upload, remove_cor_file, read_cor_upload
from app.utils.cor_extractor import extract_cor_fields
from app.routes.forms import SignupForm


logger = logging.getLogger(__name__)


@auth.route("/signup", methods=["GET", "POST"])
def signup():
    form = SignupForm()

    if form.validate_on_submit():
        try:
            extracted = extract_cor_fields(read_cor_upload(form.cor.data)["content"])
        except ValueError as exc:
            form.cor.errors.append(str(exc))
            return render_template('authentication/signup.html', form=form,
                                   hide_nav=True, hide_header=True, form_data=request.form)
        try:
            cor_filename = save_cor_upload(form.cor.data)
        except ValueError as exc:
            form.cor.errors.append(str(exc))
            return render_template('authentication/signup.html', form=form,
                                   hide_nav=True, hide_header=True, form_data=request.form)
        except OSError:
            logger.exception('Could not save COR upload')
            flash('Could not save your COR. Please try again.', 'danger')
            return render_template('authentication/signup.html', form=form,
                                   hide_nav=True, hide_header=True, form_data=request.form)
        success = False
        try:
            success, message = create_user(
                form.first_name.data,
                form.middle_name.data,
                form.last_name.data,
                form.student_no.data or extracted.get("student_no"),
                form.email.data,
                form.username.data,
                form.password.data,
                cor_filename=cor_filename,
            )
        finally:
            if not success:
                try:
                    remove_cor_file(cor_filename)
                except OSError:
                    logger.exception('Could not clean up unsuccessful signup COR')

        if success:
            flash("Account created successfully! Please wait for approval.", "success")
            return redirect(url_for("auth.signin"))
        else:
            flash(message, "danger")
            return render_template("authentication/signup.html", form=form,
                                   hide_nav=True, hide_header=True,
                                   form_data=request.form)

    return render_template("authentication/signup.html", form=form,
                           hide_nav=True, hide_header=True, form_data={})


@auth.route("/signup/extract-cor", methods=["POST"])
def extract_cor():
    upload = request.files.get("cor")
    try:
        document = read_cor_upload(upload)
        return jsonify(extract_cor_fields(document["content"]))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
