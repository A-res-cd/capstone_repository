from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import (
    StringField, PasswordField, HiddenField, IntegerField, SelectField, SelectMultipleField,
    BooleanField, FieldList, FormField, TextAreaField,
)
from wtforms.validators import DataRequired, Email, Length, Regexp, EqualTo, Optional, NumberRange, ValidationError
from wtforms.widgets import CheckboxInput

from app.db.advisories import MAX_ADVISORY_GROUP_STUDENTS

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


class ChangePasswordForm(FlaskForm):
    """Self-service password change from the User Information page —
    distinct from ResetPasswordForm, which is reached via the
    forgot-password/OTP flow and doesn't need the current password."""
    current_password = PasswordField("Current Password", validators=[DataRequired(message="Current password is required.")])
    new_password = PasswordField("New Password", validators=[DataRequired(), Length(min=6, message="Password must be at least 6 characters.")])
    confirm_password = PasswordField("Confirm New Password", validators=[DataRequired(), EqualTo("new_password", message="Passwords do not match.")])

class VerifyOTPForm(FlaskForm):
    otp = StringField("OTP", validators=[DataRequired(message = "Please enter the OTP."), Length(min=6, max=6, message="OTP must be 6 digits."), Regexp(r'^[0-9]{6}\Z', message="OTP must contain numbers only.")])

#ts took me 1hr to code 💀 (i see you reading the code 👀) i know it's shit man


# ── Capstone create/update forms ──────────────────────────────────────────
# Server-side validation for the repository's 2-step create/edit wizard —
# previously all raw request.form.get(...) parsing in admin.py with only
# ad-hoc checks (e.g. the adviser first/last "if not X: flash(...)" pattern).

class CapstonerRegistrationForm(FlaskForm):
    reason = TextAreaField("Capstone details", validators=[DataRequired(), Length(max=2000)])


class CapstonerReviewForm(FlaskForm):
    decision = SelectField(choices=[("approved", "Approve"), ("rejected", "Reject")], validators=[DataRequired()])
    status_reason = TextAreaField("Feedback", validators=[Optional(), Length(max=1000)])


class CapstonerAssignmentForm(FlaskForm):
    user_id = SelectField("User account", coerce=int, validators=[DataRequired()])
    credit = SelectField("Unlinked author credit", validators=[DataRequired()])
    confirmed = BooleanField("I verified that this person authored the selected capstone.", validators=[DataRequired()])


class AdvisoryGroupForm(FlaskForm):
    group_name = StringField("Group name", validators=[DataRequired(), Length(max=100)],
                             filters=[lambda value: value.strip() if value else value])


class CreateAdvisoryGroupForm(AdvisoryGroupForm):
    student_ids = SelectMultipleField("Students to add", coerce=int, validators=[
        Optional(),
        Length(max=MAX_ADVISORY_GROUP_STUDENTS, message=f"Select at most {MAX_ADVISORY_GROUP_STUDENTS} students."),
    ], option_widget=CheckboxInput())
    confirmed = BooleanField("I am assigned to advise all selected students.")


class AddAdvisoryStudentForm(FlaskForm):
    group_id = SelectField("Advisory group", coerce=int, validators=[DataRequired()])
    student_id = SelectMultipleField("Student accounts", coerce=int, option_widget=CheckboxInput(), validators=[
        DataRequired(message="Select at least one student."),
        Length(max=MAX_ADVISORY_GROUP_STUDENTS, message=f"Select at most {MAX_ADVISORY_GROUP_STUDENTS} students."),
    ])
    confirmed = BooleanField("I am assigned to advise all selected students.", validators=[DataRequired()])


class RemoveAdvisoryStudentForm(FlaskForm):
    confirmed = BooleanField("Remove from my roster only.", validators=[DataRequired()])


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

    author_id = HiddenField(validators=[Optional(), Regexp(r'^[1-9][0-9]*$', message="Invalid author ID.")])
    user_id = SelectField("Linked account", coerce=int, default=0, choices=[(0, "No linked account")])
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

    def validate_authors(self, field):
        linked_users = set()
        for author in field:
            user_id = author.user_id.data
            if not user_id:
                continue
            if not (author.first_name.data or "").strip() and not (author.last_name.data or "").strip():
                raise ValidationError("Enter the author name before linking an account.")
            if user_id in linked_users:
                raise ValidationError("Link each account to only one author per capstone.")
            linked_users.add(user_id)


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
