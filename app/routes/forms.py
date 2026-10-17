from app.utils.password_policy import validate_password
from app.utils.contact_policy import normalize_phone
from wtforms.validators import ValidationError
from flask_wtf import FlaskForm
from flask import request
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import (
    StringField, PasswordField, HiddenField, IntegerField, SelectField,
    BooleanField, FieldList, FormField,
)
from wtforms.validators import DataRequired, Email, Length, Regexp, EqualTo, Optional, NumberRange

class SigninForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(message = "Username is required."), Length(max=30)])
    password = PasswordField("password", validators=[DataRequired(message = "Password is required."), Length(max=1024)])

class SignupForm(FlaskForm):
    website = HiddenField()
    role = SelectField("Sign up as", choices=[("Student", "Student"), ("Faculty", "Faculty")], validators=[DataRequired(message="Choose an account type.")])
    cor = FileField('Verification document', validators=[
        FileAllowed(['pdf', 'jpg', 'jpeg', 'png'], 'Upload a PDF or JPG/PNG image.'),
    ])
    student_no = StringField("ID Number", validators=[Optional(), Length(max=50)])
    first_name = StringField("First Name", validators=[DataRequired(message = "Firt Name is required."), Length(max=50)])
    middle_name = StringField("Middle Name", validators=[Optional(), Length(max=50)])
    last_name = StringField("Last Name", validators=[DataRequired(message = "Last Name is required")])
    email = StringField("Recovery email", validators=[DataRequired(message="Enter an email for account recovery."), Email(message="Invalid Email format."), Length(max=254)])
    username = StringField("Username", validators=[DataRequired(message = "Username is required."), 
                                                   Regexp(r'^[a-zA-Z0-9_]{3,30}$', 
                                                          message="Username must be 3-30 characters, letters, numbers, and underscores only.")])
    
    password = PasswordField("Password", validators=[DataRequired(message = "Password is required"), 
                                                     validate_password])
    confirm_password = PasswordField("Confirm Password", validators=[DataRequired(), EqualTo("password", message="Passwords do not match.")])
    preferred_contact = SelectField("Preferred contact", choices=[("", "Choose email or phone"), ("email", "Email"), ("phone", "Phone")], default="", validators=[DataRequired(message="Choose email or phone.")])
    phone = StringField("Phone number", validators=[Optional(), Length(max=30)])

    def validate_preferred_contact(self, field):
        if field.data == "email" and not (self.email.data or '').strip():
            raise ValidationError("Enter your email address.")
        try:
            self.phone.data = normalize_phone(self.phone.data)
        except ValueError as exc:
            raise ValidationError(str(exc))
        if field.data == "phone" and not self.phone.data:
            raise ValidationError("Enter a phone number when phone is your preferred contact.")

    accept_terms = BooleanField(
        "I accept the Terms and Agreements",
        validators=[DataRequired(message="You must accept the Terms and Agreements to create an account.")]
    )
    
class SignupEmailForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=254)])
    code = StringField("Verification code", validators=[Optional(), Regexp(r'^[0-9]{6}$', message="Enter the six-digit code.")])


class ForgotPasswordForm(FlaskForm):
    delivery_channel = SelectField("Send code via", choices=[('email', 'Email'), ('sms', 'SMS to registered phone')], default='email')
    username = StringField("Username", validators = [DataRequired(message="Username is required.")])
    email = StringField("Email", validators = [DataRequired("Email is required."), Email(message="Invalid email format.")])

class ResetPasswordForm(FlaskForm):
    new_password = PasswordField("New Password", validators = [DataRequired(), validate_password])
    confirm_password = PasswordField("Confirm Password", validators = [DataRequired(), EqualTo("new_password", message="Passwords do not mathc.")])


class ChangePasswordForm(FlaskForm):
    """Self-service password change from the User Information page —
    distinct from ResetPasswordForm, which is reached via the
    forgot-password/OTP flow and doesn't need the current password."""
    current_password = PasswordField("Current Password", validators=[DataRequired(message="Current password is required.")])
    new_password = PasswordField("New Password", validators=[DataRequired(), validate_password])
    confirm_password = PasswordField("Confirm New Password", validators=[DataRequired(), EqualTo("new_password", message="Passwords do not match.")])

class VerifyOTPForm(FlaskForm):
    otp = StringField("OTP", validators=[DataRequired(message = "Please enter the OTP."), Length(min=6, max=6, message="OTP must be 6 digit."), Regexp(r'^\d{6}$', message="OTP must be numbers onyl.")])

#ts took me 1hr to code 💀 (i see you reading the code 👀) i know it's shit man


# ── Capstone create/update forms ──────────────────────────────────────────
# Server-side validation for the repository's 2-step create/edit wizard —
# previously all raw request.form.get(...) parsing in admin.py with only
# ad-hoc checks (e.g. the adviser first/last "if not X: flash(...)" pattern).

class AuthorForm(FlaskForm):
    """One author row. Blank extra slots are valid; the parent form requires
    1–5 complete authors. The adviser variant requires first/last names."""
    # Disable each subform's own CSRF field — FieldList/FormField would
    # otherwise render one nested token per row, and the outer form's
    # single token (from Flask-WTF's global CSRFProtect) already covers
    # the whole POST.
    class Meta:
        csrf = False

    first_name = StringField("First", validators=[Optional(), Length(max=100)])
    middle_name = StringField("Middle", validators=[Optional(), Length(max=100)])
    last_name = StringField("Last", validators=[Optional(), Length(max=100)])


class AdviserForm(AuthorForm):
    """Same shape as AuthorForm, but first/last are mandatory — an
    adviser is required for every capstone."""
    first_name = StringField("First", validators=[DataRequired(message="Adviser first name is required."), Length(max=100)])
    last_name = StringField("Last", validators=[DataRequired(message="Adviser last name is required."), Length(max=100)])


class CreateCapstoneForm(FlaskForm):

    capstone_id = HiddenField()

    capstone_file = FileField(
        "Upload Capstone File",
        validators=[
            FileRequired(message="Upload a capstone file first."),
            FileAllowed(
                ["pdf", "doc", "docx"],
                "Only PDF, DOC, and DOCX files are allowed"
            )
        ]
    )

    capstone_title = StringField(
        "Capstone Title",
        validators=[
            DataRequired(),
            Length(max=500)
        ]
    )

    capstone_year = IntegerField(
        "Year",
        validators=[
            DataRequired(),
            NumberRange(min=2000, max=2099)
        ]
    )

    program_id = SelectField(
        "Program",
        coerce=int,
        validators=[DataRequired()]
    )

    specialization_id = SelectField(
        "Specialization",
        coerce=int,
        validators=[DataRequired()]
    )

    semester = SelectField(
        "Semester",
        choices=[("1st", "1st Semester"), ("2nd", "2nd Semester"), ("summer", "Summer")],
        validators=[DataRequired()]
    )

    capstone_keywords = StringField(
        "Keywords",
        validators=[
            DataRequired(),
            Length(max=1000)
        ]
    )

    is_published = BooleanField("Published")
    is_utilized = BooleanField("Utilized")
    is_presented = BooleanField("Presented")
    is_copyright_registered = BooleanField(
        "Copyright Registered"
    )

    ## Authors
    authors = FieldList(
        FormField(AuthorForm),
        min_entries=1,
        max_entries=5
    )

    adviser = FormField(AdviserForm)

    def validate_authors(self, field):
        # FieldList truncates excess entries; reject them rather than lose members.
        indices = {int(key.split('-')[1]) for key in request.form
                   if key.startswith('authors-') and key.split('-')[1].isdigit()}
        if any(index >= 5 for index in indices):
            raise ValidationError('Enter between 1 and 5 authors.')
        members = [entry for entry in field
                   if any((value or '').strip() for value in entry.data.values())]
        if not members:
            raise ValidationError('Enter at least one author.')
        if any(not entry.first_name.data or not entry.first_name.data.strip()
               or not entry.last_name.data or not entry.last_name.data.strip() for entry in members):
            raise ValidationError('Each author needs a first and last name.')


class UpdateCapstoneForm(CreateCapstoneForm):
    """Same as CreateCapstoneForm, except the file isn't required — an
    edit can keep whatever file is already on record."""
    capstone_file = FileField(
        "Upload Capstone File",
        validators=[
            Optional(),
            FileAllowed(
                ["pdf", "doc", "docx"],
                "Only PDF, DOC, and DOCX files are allowed"
            )
        ]
    )
