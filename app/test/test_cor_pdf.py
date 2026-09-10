from io import BytesIO
from pathlib import Path

import pdfplumber
import pytest

from app.utils.cor_extractor import extract_cor_fields


SAMPLE_COR = (
    Path(__file__).parents[1]
    / "static"
    / "uploads"
    / "registration"
    / "Sapin_Aaries_M._3e7f3448731c472d93c9912b893e73ac.pdf"
)


def test_sample_cor_pdf_is_readable_and_image_based():
    content = SAMPLE_COR.read_bytes()

    with pdfplumber.open(BytesIO(content)) as pdf:
        assert len(pdf.pages) == 1
        assert len(pdf.pages[0].images) == 1
        assert not (pdf.pages[0].extract_text() or "").strip()


def test_sample_cor_extracts_expected_fields_when_ocr_is_available():
    fields = extract_cor_fields(SAMPLE_COR.read_bytes())
    if fields["warning"]:
        pytest.skip(fields["warning"])

    assert fields["registration_no"] == "5361807"
    assert fields["student_no"] == "SUM2023-01246"
    assert fields["first_name"] == "Aaries"
    assert fields["middle_name"] == "M"
    assert fields["last_name"] == "Sapin"
