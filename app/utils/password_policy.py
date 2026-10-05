"""Shared policy for newly set passwords; existing credentials remain valid."""
from wtforms.validators import ValidationError

PASSWORD_MIN = 15
PASSWORD_MAX = 128
PASSWORD_MESSAGE = 'Use 15–128 characters. Spaces and passphrases are allowed.'


def password_error(value):
    if not isinstance(value, str) or not PASSWORD_MIN <= len(value) <= PASSWORD_MAX:
        return PASSWORD_MESSAGE
    return None


def validate_password(form, field):
    error = password_error(field.data)
    if error:
        raise ValidationError(error)
