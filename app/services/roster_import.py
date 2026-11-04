"""Shared roster normalization; identifiers remain text in every document format."""
from pathlib import Path
import re
from email_validator import validate_email, EmailNotValidError
from app.services.student_documents import HEADERS

MAX_BYTES = 5 * 1024 * 1024
NUMBER = re.compile(r'^[A-Z0-9][A-Z0-9-]{0,49}$')

def normalize_number(value):
    return str(value or '').strip().upper()

def valid_number(value):
    return bool(NUMBER.fullmatch(value) and not re.fullmatch(r'\d+(?:\.\d+)?E[+-]?\d+',value))

def normalize_email(value):
    return str(value or '').strip().lower()

def valid_email(value):
    if len(value)>254:
        return False
    try:
        validate_email(value,check_deliverability=False)
        return True
    except EmailNotValidError:
        return False

def normalize_candidate(candidate):
    accepted,skipped,display,seen=[],[],[],set()
    for raw in candidate['records']:
        number=normalize_number(raw.get('university_no'))
        source=raw['source']
        row={name:str(raw.get(name) or '').strip() for name in ('first_name','middle_name','last_name','email')}
        row.update(university_no=number,email=normalize_email(raw.get('email')),source=source,source_row=source['row'])
        reason=None
        if raw.get('repeated_header'):
            reason='Repeated table header; not a student.'
        elif not raw.get('identifier_is_text',True) or not valid_number(number):
            reason='Empty, numeric/scientific or invalid identifier; keep student numbers as text.'
        elif number in seen:
            reason='Duplicate university number; first occurrence retained.'
        if number and not raw.get('repeated_header'):
            seen.add(number)
        if not reason and not valid_email(row['email']):
            reason='Invalid email.'
        if not reason and (not row['first_name'] or not row['last_name']):
            reason='First and last names are required.'
        if not reason and any(len(row[key])>100 for key in ('first_name','middle_name','last_name')):
            reason='Name exceeds 100 characters.'
        if reason:
            skipped.append({'row':source['row'],'source':source,'reason':reason})
        else:
            accepted.append(row)
        display.append({**row,'issue':reason})
    return accepted,skipped,display

def parse_upload(upload):
    # Trusted internal adapter; HTTP extraction uses the bounded worker and staging.
    from app.services.student_documents import extract_document
    data=upload.stream.read(MAX_BYTES+1)
    extracted=extract_document(data,Path(upload.filename or '').suffix.lower())
    if len(extracted['candidates'])!=1:
        raise ValueError('Select the intended table through upload preview.')
    accepted,skipped,_=normalize_candidate(extracted['candidates'][0])
    return accepted,skipped
