from io import BytesIO

import pdfplumber
import pytest
from PIL import Image, ImageDraw, ImageFont

from app.utils.cor_extractor import configure_tesseract, extract_cor_fields


@pytest.fixture(scope='module')
def sample_cor_pdf():
    """Synthetic scanned COR: one image, no text layer or personal uploads."""
    with Image.new('RGB', (1600, 1000), 'white') as image:
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=38)
        for y, text in ((60, 'CERTIFICATE OF REGISTRATION'),
                        (240, 'Registration No: 1234567'),
                        (400, 'Name: DOE, ALEX M.'),
                        (560, 'Student No: SUM2026-12345')):
            draw.text((100, y), text, fill='black', font=font)
        output = BytesIO()
        image.save(output, format='PDF', resolution=150)
    return output.getvalue()


def test_sample_cor_pdf_is_readable_and_image_based(sample_cor_pdf):
    content = sample_cor_pdf

    with pdfplumber.open(BytesIO(content)) as pdf:
        assert len(pdf.pages) == 1
        assert len(pdf.pages[0].images) == 1
        assert not (pdf.pages[0].extract_text() or "").strip()


def test_sample_cor_extracts_expected_fields_when_ocr_is_available(sample_cor_pdf):
    pytesseract = pytest.importorskip('pytesseract')
    configure_tesseract()
    try:
        pytesseract.get_tesseract_version()
    except pytesseract.TesseractNotFoundError:
        pytest.skip('Tesseract OCR is not installed')
    fields = extract_cor_fields(sample_cor_pdf)
    assert not fields['warning'], fields['warning']

    assert fields["registration_no"] == "1234567"
    assert fields["student_no"] == "SUM2026-12345"
    assert fields["first_name"] == "Alex"
    assert fields["middle_name"] == "M"
    assert fields["last_name"] == "Doe"
