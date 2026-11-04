"""Conditional certificate requirements in the capstone Flask-WTF forms."""
from io import BytesIO

from flask import Flask
import pytest

from app.routes.forms import CreateCapstoneForm, UpdateCapstoneForm


def payload():
    return {
        'capstone_file': (BytesIO(b'%PDF-1.4 manuscript'), 'manuscript.pdf'),
        'capstone_title': 'Test capstone', 'capstone_year': '2026',
        'program_id': '1', 'specialization_id': '1', 'semester': '1st',
        'capstone_keywords': 'testing',
        'authors-0-first_name': 'Ada', 'authors-0-last_name': 'Lovelace',
        'adviser-first_name': 'Grace', 'adviser-last_name': 'Hopper',
    }


def validate(data, form_type=CreateCapstoneForm, existing=None):
    app = Flask(__name__)
    app.config.update(SECRET_KEY='test', WTF_CSRF_ENABLED=False)
    with app.test_request_context(method='POST', data=data):
        form = form_type()
        form.program_id.choices = [(1, 'Program')]
        form.specialization_id.choices = [(1, 'Specialization')]
        form.existing_certificates = existing or {}
        valid = form.validate()
        return valid, form.errors


@pytest.mark.parametrize('utilized,copyright', [(False, False), (True, False), (False, True), (True, True)])
def test_conditional_certificate_forms(utilized, copyright):
    data = payload()
    if utilized:
        data.update(is_utilized='y', utilization_date='2026-11-05',
                    utilization_file=(BytesIO(b'%PDF-1.4 certificate'), 'utilization.pdf'))
    if copyright:
        data.update(is_copyright_registered='y', copyright_cert_num='CERT-1', copyright_cert_date='2026-11-05',
                    copyright_cert_file=(BytesIO(b'%PDF-1.4 certificate'), 'copyright.pdf'))
    valid, errors = validate(data)
    assert valid, errors


@pytest.mark.parametrize('flag,fields', [
    ('is_utilized', ('utilization_date', 'utilization_file')),
    ('is_copyright_registered', ('copyright_cert_num', 'copyright_cert_date', 'copyright_cert_file')),
])
def test_selected_certificate_requires_details_and_file(flag, fields):
    data = payload()
    data[flag] = 'y'
    valid, errors = validate(data)
    assert not valid
    assert all(name in errors for name in fields)


def test_edit_keeps_existing_certificate_file_but_rejects_invalid_replacement():
    data = payload()
    data.update(is_utilized='y', utilization_date='2026-11-05')
    valid, errors = validate(data, UpdateCapstoneForm, {'utilization_file': 'uploads/existing.pdf'})
    assert valid, errors
    data = payload()
    data.update(is_utilized='y', utilization_date='not-a-date',
                utilization_file=(BytesIO(b'bad'), 'certificate.exe'))
    valid, errors = validate(data, UpdateCapstoneForm, {'utilization_file': 'uploads/existing.pdf'})
    assert not valid and 'utilization_file' in errors and 'utilization_date' in errors
