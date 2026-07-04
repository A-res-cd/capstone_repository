from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField
from wtforms.validators import DataRequired, Email, Length ,Regexp, EqualTo, Optional

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
