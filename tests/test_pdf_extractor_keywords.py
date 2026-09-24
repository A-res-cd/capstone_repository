from unittest.mock import MagicMock, patch

from app.utils import pdf_extractor


def test_keyword_suggestions_never_exceed_six():
    text = (
        "Smart irrigation monitoring using wireless sensors. "
        "Soil moisture sensors track water usage and crop health. "
        "Weather forecasting and automated irrigation improve water conservation."
    )
    keywords = pdf_extractor._suggest_keywords_yake(text, top_n=20)

    assert 0 < len(keywords) <= 6
    assert all(keyword.lower() in text.lower() for keyword in keywords)


def test_extraction_uses_title_and_abstract_for_topic_keywords():
    pdf = MagicMock()
    pdf.pages = [MagicMock() for _ in range(3)]
    pdf.pages[0].extract_text.return_value = "Smart Irrigation\nA CAPSTONE PROJECT"
    pdf.pages[1].extract_text.return_value = "TABLE OF CONTENTS"
    pdf.pages[2].extract_text.return_value = "ABSTRACT\nSoil moisture sensors conserve water."
    with patch.object(pdf_extractor.pdfplumber, 'open') as open_pdf:
        open_pdf.return_value.__enter__.return_value = pdf
        with patch.object(pdf_extractor, '_suggest_keywords_yake', return_value=['soil moisture']) as suggest:
            result = pdf_extractor.extract_capstone_data('manuscript.pdf')

    suggest.assert_called_once_with('Smart Irrigation\nSoil moisture sensors conserve water.')
    assert result['keywords'] == ['soil moisture']


def test_short_manuscript_can_suggest_keywords_from_title():
    pdf = MagicMock()
    pdf.pages = [MagicMock()]
    pdf.pages[0].extract_text.return_value = "Smart Irrigation\nA CAPSTONE PROJECT"
    with patch.object(pdf_extractor.pdfplumber, 'open') as open_pdf:
        open_pdf.return_value.__enter__.return_value = pdf
        with patch.object(pdf_extractor, '_suggest_keywords_yake', return_value=['smart irrigation']) as suggest:
            result = pdf_extractor.extract_capstone_data('manuscript.pdf')

    suggest.assert_called_once_with('Smart Irrigation')
    assert result['keywords'] == ['smart irrigation']
    assert '_error' not in result
