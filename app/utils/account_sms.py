"""Server-side Semaphore delivery; never log credentials or OTPs."""
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import current_app

from app.utils.contact_policy import normalize_phone


def _send_sms(phone, message, *, code=None):
    api_key = current_app.config.get('SEMAPHORE_API_KEY', '')
    if not api_key:
        raise OSError('SMS delivery is not configured.')
    try:
        phone = normalize_phone(phone)
    except ValueError:
        raise OSError('SMS delivery requires a Philippine mobile number.') from None
    if not phone or len(phone) != 13 or not phone.startswith('+639'):
        raise OSError('SMS delivery requires a Philippine mobile number.')
    payload = {
        'apikey': api_key,
        'number': phone[1:],
        'message': message,
    }
    if not isinstance(message, str) or not message.strip():
        raise OSError('SMS message must not be empty.')
    if code is not None:
        payload['code'] = code
    sender = current_app.config.get('SEMAPHORE_SENDER_NAME', '')
    if sender:
        payload['sendername'] = sender
    endpoint = 'otp' if code is not None else 'messages'
    request = Request(f'https://api.semaphore.co/api/v4/{endpoint}',
                      data=urlencode(payload).encode('utf-8'), method='POST')
    try:
        with urlopen(request, timeout=10) as response:
            result = json.load(response)
    except (HTTPError, URLError, OSError, ValueError):
        raise OSError('SMS provider is unavailable. Please try again.') from None
    if (not isinstance(result, list) or len(result) != 1
            or not isinstance(result[0], dict) or not result[0].get('message_id')
            or str(result[0].get('status', '')).lower() not in ('queued', 'pending', 'sent')):
        raise OSError('SMS provider did not accept the message.')
    return result[0]['message_id']


def send_sms(phone, message):
    """Send one notification; acceptance does not confirm handset delivery."""
    return _send_sms(phone, message)


def send_contact_change_sms(phone, code):
    return _send_sms(phone, 'Your CAPRE recovery contact verification code is {otp}. Expires in 15 minutes. Do not share it.', code=code)


def send_password_reset_sms(phone, code, expiry_minutes):
    return _send_sms(
        phone,
        f'Your CAPRE password reset code is {{otp}}. Expires in {expiry_minutes} minutes. Do not share this code.',
        code=code,
    )
