"""Contact preferences do not change the email-based recovery channel."""
import re


def normalize_phone(value):
    value = re.sub(r'[\s()\-]', '', value or '')
    if value.startswith('09') and len(value) == 11:
        value = '+63' + value[1:]
    if value and not re.fullmatch(r'\+[1-9][0-9]{7,14}', value):
        raise ValueError('Use a valid international phone number, such as +639171234567.')
    return value
