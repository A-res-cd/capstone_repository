from unittest.mock import MagicMock, patch

from app.utils import pdf_extractor
import pytest


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


@pytest.mark.parametrize('title,expected', [
    ('WEB-BASED RECORD MANAGEMENT AND DISPATCHING SYSTEM FOR TRUCKING SERVICES', ['record management', 'trucking services']),
    ('DESIGN AND DEVELOPMENT OF ACADEMIC INFORMATION MANAGEMENT SYSTEM FOR SENIOR HIGHSCHOOL - EDUARDO L. JOSON MEMORIAL HIGHSCHOOL', ['academic information']),
    ('EvalOn: A WEB-BASED FACULTY EVALUATION SYSTEM FOR SAINT ROSE OF LIMA CATHOLIC SCHOOL', ['faculty evaluation']),
    ('Implementation of Wireless Local Area Network at SANTA ROSA FIRE STATION', ['wireless local area network']),
    ('Extension of Internet Connectivity at Maligaya National High School Using Cat6 Ethernet Cable', ['internet connectivity', 'cat6 ethernet cable']),
])
def test_dataset_topic_keywords_exclude_institutions_and_methodology(title, expected):
    text = title + '\nResearchers used the Software Development Life Cycle and Spiral Model. Nueva Ecija school respondents evaluated the system.'
    keywords = pdf_extractor._suggest_keywords_yake(text)
    lowered = [phrase.casefold() for phrase in keywords]
    assert all(phrase in lowered for phrase in expected)
    assert not any(term in phrase for phrase in lowered for term in
                   ['school', 'saint rose', 'santa rosa', 'maligaya', 'nueva ecija', 'life cycle', 'spiral model'])
    assert len(keywords) <= 6


def test_abstract_can_precede_table_of_contents():
    page = MagicMock()
    page.extract_text.return_value = 'ABSTRACT\nSoil sensors conserve water.'
    assert pdf_extractor._parse_abstract_page([page]) == (1, 'Soil sensors conserve water.')
