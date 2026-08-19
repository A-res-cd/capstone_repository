from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import (
    StringField, PasswordField, HiddenField, IntegerField, SelectField,
    BooleanField, FieldList, FormField,
)
from wtforms.validators import DataRequired, Email, Length, Regexp, EqualTo, Optional, NumberRange

class SigninForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(message = "Username is required.")])
    password = PasswordField("password", validators=[DataRequired(message = "Password is required.")])

class SignupForm(FlaskForm):
    first_name = StringField("First Name", validators=[DataRequired(message = "Firt Name is required."), Length(max=50)])
    middle_name = StringField("Middle Name", validators=[Optional(), Length(max=50)])
    last_name = StringField("Last Name", validators=[DataRequired(message = "Last Name is required")])
    email = StringField("Email", validators=[DataRequired(message = "Email is required."), Email(message="Invalid Email format.")])
    username = StringField("Username", validators=[DataRequired(message = "Username is required."), 
                                                   Regexp(r'^[a-zA-Z0-9_]{3,30}$', 
                                                          message="Username must be 3-30 characters, letters, numbers, and underscores only.")])
    
    password = PasswordField("Password", validators=[DataRequired(message = "Password is required"), 
                                                     Length(min = 6, message = "Password must be at least 6 characters.")])
    
class ForgotPasswordForm(FlaskForm):
    username = StringField("Username", validators = [DataRequired(message="Username is required.")])
    email = StringField("Email", validators = [DataRequired("Email is required."), Email(message="Invalid email format.")])

class ResetPasswordForm(FlaskForm):
    new_password = PasswordField("New Password", validators = [DataRequired(), Length(min=6, message="Password must be at least 6 characters.")])
    confirm_password = PasswordField("Confirm Password", validators = [DataRequired(), EqualTo("new_password", message="Passwords do not mathc.")])

class VerifyOTPForm(FlaskForm):
    otp = StringField("OTP", validators=[DataRequired(message = "Please enter the OTP."), Length(min=6, max=6, message="OTP must be 6 digit."), Regexp(r'^\d{6}$', message="OTP must be numbers onyl.")])

#ts took me 1hr to code 💀 (i see you reading the code 👀) i know it's shit man


# ── Capstone create/update forms ──────────────────────────────────────────
# Server-side validation for the repository's 2-step create/edit wizard —
# previously all raw request.form.get(...) parsing in admin.py with only
# ad-hoc checks (e.g. the adviser first/last "if not X: flash(...)" pattern).

class AuthorForm(FlaskForm):
    """One author row. Base form is intentionally lenient — only 1 of the
    4 author slots is actually required by the app, so a blank row must
    stay valid; the adviser variant below tightens this."""
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
    adviser is required for every capstone, unlike the 4 author slots."""
    first_name = StringField("First", validators=[DataRequired(message="Adviser first name is required."), Length(max=100)])
    last_name = StringField("Last", validators=[DataRequired(message="Adviser last name is required."), Length(max=100)])


class CreateCapstoneForm(FlaskForm):

    capstone_id = HiddenField()
    extracted_filename = HiddenField()

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

    citation_count = IntegerField(
        "Citation Count",
        default=0,
        validators=[
            Optional(),
            NumberRange(
                min=0,
                message="Citation count cannot be negetive."
            )
        ]
    )

    capstone_keywords = StringField(
        "Keywords",
        validators=[
            DataRequired(),
            Length(max=1000)
        ]
    )

    is_utilized = BooleanField("Utilized")
    is_presented = BooleanField("Presented")
    is_copyright_registered = BooleanField(
        "Copyright Registered"
    )

    ## Authors
    authors = FieldList(
        FormField(AuthorForm),
        min_entries=4,
        max_entries=4
    )

    adviser = FormField(AdviserForm)


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
