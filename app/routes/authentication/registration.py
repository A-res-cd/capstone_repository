"""Authentication registration routes and local helpers."""
from . import auth
from flask import flash, render_template, request, redirect, url_for, jsonify, session
import logging
import re
import time
import psycopg2
from smtplib import SMTPException
from pathlib import Path
from app import mail
from app.db.auth import create_user
from app.db.signup_verification import create_email_code, verify_email_code, signup_email_is_verified, EXPIRY_MINUTES
from app.utils.account_emails import signup_verification_email
from app.utils.cor_upload import save_cor_document, remove_cor_file, read_cor_upload
from app.utils.document_processing import DocumentBusy, DocumentTimeout
from app.routes.forms import SignupForm, SignupEmailForm


logger = logging.getLogger(__name__)


def signup_form_ready(form):
    started_at = session.get('signup_started_at')
    return (not form.website.data and isinstance(started_at, (int, float))
            and 2 <= time.time() - started_at <= 3600)


@auth.route("/signup/verify-email", methods=["GET", "POST"])
def verify_signup_email():
    form = SignupEmailForm()
    if request.method == 'POST' and request.form.get('action') == 'send':
        form.code.raw_data = []
        form.code.data = ''
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        action = request.form.get('action')
        if action == 'send':
            previous_id = session.pop('signup_email_verification_id', None)
            session.pop('signup_verified_email', None)
            try:
                verification_id, code = create_email_code(email, previous_id)
                mail.send(signup_verification_email(email, code, EXPIRY_MINUTES))
            except (SMTPException, OSError, AssertionError, psycopg2.Error):
                logger.exception('Signup verification email could not be delivered')
                flash('Could not send your verification code. Please try again later.', 'danger')
            else:
                session['signup_email_verification_id'] = verification_id
                flash('Code sent. Check your inbox and spam folder. It expires in 15 minutes.', 'success')
        elif action == 'verify':
            try:
                verified = bool(form.code.data) and verify_email_code(session.get('signup_email_verification_id'), email, form.code.data)
            except psycopg2.Error:
                logger.exception('Signup email verification unavailable')
                flash('Email verification is temporarily unavailable. Please try again later.', 'danger')
                return render_template('authentication/verify_signup_email.html', form=form,
                                       hide_nav=True, hide_header=True), 503
            if verified:
                session['signup_verified_email'] = email
                flash('Email verified. Return to your signup tab and finish creating your account.', 'success')
            else:
                form.code.errors.append('Invalid or expired code. After five incorrect attempts, request a new code.')
        else:
            form.code.errors.append('Choose Send code or Verify email.')
    elif request.method == 'GET':
        form.email.data = session.get('signup_verified_email', '')
    return render_template('authentication/verify_signup_email.html', form=form,
                           hide_nav=True, hide_header=True)


@auth.route("/signup", methods=["GET", "POST"])
def signup():
    form = SignupForm()

    if request.method == 'GET':
        session['signup_started_at'] = time.time()
        form.email.data = session.get('signup_verified_email', '')
    elif not signup_form_ready(form):
        flash('Please open the signup page and complete the form before submitting.', 'danger')
        return render_template('authentication/signup.html', form=form,
                               hide_nav=True, hide_header=True, form_data=request.form), 400

    if form.validate_on_submit() and form.cor.data and form.cor.data.filename:
        verification_id = session.get('signup_email_verification_id')
        try:
            verified = signup_email_is_verified(verification_id, form.email.data)
        except psycopg2.Error:
            logger.exception('Signup email verification unavailable')
            flash('Email verification is temporarily unavailable. Please try again later.', 'danger')
            return render_template('authentication/signup.html', form=form,
                                   hide_nav=True, hide_header=True, form_data=request.form), 503
        if not verified:
            form.email.errors.append('Verify this email before creating your account. Use the Verify email link below.')
            return render_template('authentication/signup.html', form=form,
                                   hide_nav=True, hide_header=True, form_data=request.form)
        try:
            document = read_cor_upload(form.cor.data, extract=(form.role.data == 'Faculty' or not form.student_no.data))
            if form.role.data == "Student" and Path(document["filename"]).suffix.lower() != ".pdf":
                raise ValueError("Students must upload their COR as a PDF.")
            if form.role.data == "Faculty" and Path(document["filename"]).suffix.lower() == ".pdf":
                raise ValueError("Faculty must upload a JPG or PNG image of their ID.")
            if form.role.data == "Faculty" and not re.fullmatch(r"\d{3,4}", (form.student_no.data or "").strip()):
                form.student_no.errors.append("Faculty ID must be 3–4 digits.")
                return render_template('authentication/signup.html', form=form,
                                       hide_nav=True, hide_header=True, form_data=request.form)
            extracted = document['fields']
        except ValueError as exc:
            form.cor.errors.append(str(exc))
            return render_template('authentication/signup.html', form=form,
                                   hide_nav=True, hide_header=True, form_data=request.form)
        try:
            cor_filename = save_cor_document(document)
        except ValueError as exc:
            form.cor.errors.append(str(exc))
            return render_template('authentication/signup.html', form=form,
                                   hide_nav=True, hide_header=True, form_data=request.form)
        except OSError as exc:
            logger.exception('Could not save COR upload')
            flash(f'Could not save your verification document: {exc}. Please try again.', 'danger')
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
                preferred_contact=form.preferred_contact.data, phone=form.phone.data,
                terms_version="2026-10-03",
                requested_role=form.role.data,
                signup_verification_id=verification_id,
            )
        finally:
            if not success:
                try:
                    remove_cor_file(cor_filename)
                except OSError:
                    logger.exception('Could not clean up unsuccessful signup COR')

        if success:
            for key in ('signup_email_verification_id', 'signup_verified_email', 'signup_started_at'):
                session.pop(key, None)
            flash("Account created successfully! Please wait for approval.", "success")
            return redirect(url_for("auth.signin"))
        else:
            flash(message, "danger")
            return render_template("authentication/signup.html", form=form,
                                   hide_nav=True, hide_header=True,
                                   form_data=request.form)

    if request.method == "POST" and (not form.cor.data or not form.cor.data.filename):
        form.cor.errors.append("Upload your COR PDF or faculty ID image.")
    return render_template("authentication/signup.html", form=form,
                           hide_nav=True, hide_header=True, form_data={})


@auth.route("/signup/extract-cor", methods=["POST"])
def extract_cor():
    try:
        if not signup_email_is_verified(session.get('signup_email_verification_id'), session.get('signup_verified_email', '')):
            return jsonify({'error': 'Verify your signup email before automatic extraction.'}), 403
    except psycopg2.Error:
        return jsonify({'error': 'Document processing is unavailable. Enter details manually.'}), 503
    upload = request.files.get("cor")
    selected_role = request.form.get("role")
    if selected_role not in ("Student", "Faculty"):
        return jsonify({"error": "Choose Student or Faculty first."}), 400
    try:
        extension = Path(upload.filename).suffix.lower() if upload else ''
        if selected_role == 'Faculty' and extension == '.pdf':
            raise ValueError('Faculty must upload a JPG or PNG image of their ID.')
        if selected_role == 'Student' and extension != '.pdf':
            raise ValueError('Students must upload their COR as a PDF.')
        document = read_cor_upload(upload, extract=True)
        return jsonify(document['fields'])
    except DocumentBusy as exc:
        return jsonify({'error': str(exc)}), 503
    except DocumentTimeout as exc:
        return jsonify({'error': str(exc)}), 422
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
