"""CAPRE account messages with matching HTML and plain-text alternatives."""
from flask import render_template
from flask_mail import Message


def _message(subject, email, **context):
    return Message(
        subject=subject,
        recipients=[email],
        body=render_template('emails/account_notice.txt', **context),
        html=render_template('emails/account_notice.html', **context),
    )


def password_reset_email(email, username, code, expiry_minutes):
    return _message(
        'Your CAPRE password reset code', email,
        name=username or 'there', category='Account security',
        title='Reset your password',
        preview='Use your one-time code to continue your CAPRE password reset.',
        introduction='We received a request to reset the password for your CAPRE account.',
        code=str(code), expiry_minutes=expiry_minutes,
        instruction='Enter this code on the CAPRE password reset page to continue. You will then be able to choose a new password.',
        note='If you did not request this, you can ignore this email. This request has not changed your password.',
        security='Enter the code only in CAPRE. Do not share it with anyone or send it in a reply.',
    )


def verification_email(recipient, decision, reason):
    approved = decision == 'approved'
    return _message(
        'Your CAPRE account has been verified' if approved else 'Update on your CAPRE account verification',
        recipient['email'], name=recipient.get('full_name') or 'there',
        category='Account verification',
        title='Your account is ready' if approved else 'An update on your account',
        preview='Your account has been approved. You can now sign in.' if approved else 'Your account verification result and reviewer feedback are available.',
        introduction='Your CAPRE account has been verified. You may now sign in.' if approved else 'Your CAPRE account verification was rejected. Please review the feedback below.',
        status='VERIFIED' if approved else 'NOT APPROVED',
        reason=None if approved else reason or 'No reason was provided.',
        instruction='Open CAPRE and sign in using your existing username and password.' if approved else 'Contact your account verifier or the system administrator for help with the feedback and next steps.',
        note='This message confirms account verification only; it does not grant authorship of a capstone.',
        security='Keep your password private. Never share your password or one-time codes with another person.',
    )
