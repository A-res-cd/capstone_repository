from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
import subprocess
import sys
import time

from flask import Flask
from PIL import Image
import pytest

from app.routes.authentication import registration
from app.utils import cor_extractor, document_processing as processing
from app.utils.cor_upload import read_cor_upload
from tests.test_original_branch_features import feature_app, feature_db, isolated_database, pdf_bytes
from werkzeug.datastructures import FileStorage


def text_pdf(text):
    # Minimal embedded-font text page with a rebuilt cross-reference table.
    stream = ('BT /F1 12 Tf 20 200 Td (' + text + ') Tj ET').encode()
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 400] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',
               b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    data, offsets = b'%PDF-1.4\n', [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += str(number).encode() + b' 0 obj\n' + obj + b'\nendobj\n'
    xref = len(data)
    data += b'xref\n0 6\n0000000000 65535 f \n'
    data += b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
    return data + f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()


def test_small_pdf_extracts_in_worker():
    result = processing.process_document(text_pdf('Student No: 2017100890'), '.pdf', 'extract')
    assert result['student_no'] == '2017100890'


@pytest.mark.parametrize('dimensions', [b'999999999 999999999', b'-1 792', b'0 792'])
def test_hostile_dimensions_rejected(dimensions):
    content = pdf_bytes().replace(b'300 400', dimensions)
    with pytest.raises(ValueError):
        processing.process_document(content, '.pdf')


def test_pdf_user_unit_cannot_bypass_raster_budget():
    content = pdf_bytes().replace(b'/MediaBox', b'/UserUnit 1000000 /MediaBox')
    with pytest.raises(ValueError):
        processing.process_document(content, '.pdf')


def test_total_page_raster_budget():
    from tests.test_manuscript_reader import pdf_bytes as many_pages
    # Large square pages hit the four-million-pixel ceiling; eleven exceed the job budget.
    content = many_pages(11).replace(b'300 400', b'1000 1000')
    with pytest.raises(ValueError):
        processing.process_document(content, '.pdf')


def test_decoded_image_pixels_rejected():
    output = BytesIO()
    with Image.new('RGB', (4100, 4100)) as image:
        image.save(output, format='PNG')
    with pytest.raises(ValueError):
        read_cor_upload(FileStorage(BytesIO(output.getvalue()), filename='id.png'))


def test_valid_faculty_image_and_malformed_document():
    output = BytesIO()
    with Image.new('RGB', (640, 480)) as image:
        image.save(output, format='PNG')
    assert processing.process_document(output.getvalue(), '.png') == {}
    with pytest.raises(ValueError, match='budget'):
        processing.process_document(b'%PDF-1.4\nmalformed', '.pdf')


def test_extracted_text_budget():
    app = Flask(__name__)
    app.config['DOCUMENT_TEXT_CHARS'] = 10
    # Use local admission to isolate the parser budget from database admission.
    with app.app_context(), pytest.MonkeyPatch.context() as patch:
        @contextmanager
        def slot():
            yield
        patch.setattr(processing, '_slot', slot)
        with pytest.raises(ValueError):
            processing.process_document(text_pdf('Student No: 2017100890'), '.pdf', 'extract')


def test_worker_receives_no_application_credentials(monkeypatch):
    monkeypatch.setenv('PG_PASSWORD', 'private-test-password')
    monkeypatch.setenv('SECRET_KEY', 'private-test-secret')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'private-test-cloud-key')
    real_popen = subprocess.Popen
    seen = []
    def launch(*args, **kwargs):
        seen.append(kwargs['env'])
        return real_popen(*args, **kwargs)
    monkeypatch.setattr(processing.subprocess, 'Popen', launch)
    assert processing.process_document(pdf_bytes(), '.pdf') == {}
    assert not any(key in seen[0] for key in ('PG_PASSWORD', 'SECRET_KEY', 'SUPABASE_SERVICE_ROLE_KEY'))


def test_deadline_kills_ocr_descendant_and_cleans_files(tmp_path, monkeypatch):
    app = Flask(__name__)
    app.config['DOCUMENT_JOB_SECONDS'] = 1
    sentinel = tmp_path / 'descendant-survived'
    child_code = 'import time; from pathlib import Path; time.sleep(3); Path(' + repr(str(sentinel)) + ').write_text("alive")'
    parent_code = ('import sys,subprocess,time; sys.stdin.buffer.read(); '
                   'subprocess.Popen([sys.executable,"-c",' + repr(child_code) + ']); time.sleep(30)')
    real_popen = subprocess.Popen
    directories = []
    def launch(args, **kwargs):
        directories.append(kwargs['cwd'])
        return real_popen([sys.executable, '-c', parent_code], **kwargs)
    @contextmanager
    def slot():
        yield
    monkeypatch.setattr(processing, '_slot', slot)
    monkeypatch.setattr(processing.subprocess, 'Popen', launch)
    with app.app_context(), pytest.raises(processing.DocumentTimeout):
        processing.process_document(pdf_bytes(), '.pdf')
    time.sleep(3.2)
    assert not sentinel.exists()
    assert all(not Path(directory).exists() for directory in directories)


def test_shared_slots_reject_promptly_without_blocking_login(feature_app, feature_db):
    with feature_app.app_context(), processing._slot():
        def try_slot():
            with feature_app.app_context(), pytest.raises(processing.DocumentBusy):
                with processing._slot():
                    pytest.fail('A second processing slot was granted.')
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: try_slot(), range(2)))
        assert feature_app.test_client().get('/signin').status_code == 200
    with feature_app.app_context():
        assert processing.process_document(pdf_bytes(), '.pdf') == {}


def test_automatic_extraction_requires_email_proof(feature_app, monkeypatch):
    monkeypatch.setattr(registration, 'signup_email_is_verified', lambda *args: False)
    monkeypatch.setattr(registration, 'read_cor_upload', lambda *args, **kwargs: pytest.fail('Parser must not be called'))
    assert feature_app.test_client().post('/signup/extract-cor').status_code == 403


@pytest.mark.parametrize('error,status', [(processing.DocumentBusy('busy'), 503),
                                       (processing.DocumentTimeout('timeout'), 422), (ValueError('invalid'), 400)])
def test_extraction_failure_is_stable_and_manual_form_available(feature_app, monkeypatch, error, status):
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(registration, 'read_cor_upload', fail)
    client = feature_app.test_client()
    response = client.post('/signup/extract-cor', data={'role': 'Student', 'cor': (BytesIO(pdf_bytes()), 'cor.pdf')})
    assert response.status_code == status and response.is_json
    assert client.get('/signup').status_code == 200


def test_ocr_calls_have_timeouts_and_bounded_render(monkeypatch):
    calls = []
    class Page:
        width, height = 612, 792
        def to_image(self, resolution):
            assert resolution <= 2000 * 72 / 792
            return type('Rendered', (), {'original': Image.new('RGB', (100, 100))})()
    def ocr(image, **kwargs):
        calls.append(kwargs)
        assert kwargs['timeout'] == 10
        return 'Student No: 2017100890'
    monkeypatch.setattr(cor_extractor, 'configure_tesseract', lambda: None)
    monkeypatch.setattr(cor_extractor.pytesseract, 'image_to_string', ocr)
    assert cor_extractor._ocr_page(Page())[0]
    assert len(calls) == 2
