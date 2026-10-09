"""Shared policy for newly set passwords; existing credentials remain valid."""
import re
from wtforms.validators import ValidationError

PASSWORD_MIN = 8
PASSWORD_MAX = 12
PASSWORD_MESSAGE = 'Use 8–12 characters with uppercase, lowercase and numbers.'


def password_error(value):
    if not isinstance(value, str) or not PASSWORD_MIN <= len(value) <= PASSWORD_MAX:
        return PASSWORD_MESSAGE
    if not all(re.search(pattern, value) for pattern in (r'[A-Z]', r'[a-z]', r'[0-9]')):
        return PASSWORD_MESSAGE
    return None


def validate_password(form, field):
    error = password_error(field.data)
    if error:
        raise ValidationError(error)
