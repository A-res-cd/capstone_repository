from app.utils.pdf_extractor import _parse_adviser_from_approval, _parse_name_string
from app.utils.pdf_extractor import _parse_cover_authors, _parse_adviser_mention
import pytest


def test_author_supports_multiple_first_names_initials_and_particle_surname():
    assert _parse_name_string("DELA CRUZ, ALVIN JAMES DC.") == {
        "first": "Alvin James",
        "middle": "DC.",
        "last": "Dela Cruz",
    }


def test_author_extracts_full_middle_name_without_initial_period():
    assert _parse_name_string("OLMO, ELMARK JOSH") == {
        "first": "Elmark",
        "middle": "Josh",
        "last": "Olmo",
    }


def test_dataset_author_preserves_three_given_names_without_initials():
    assert _parse_name_string('DIEGO, ARIS KWONG SHENG') == {
        'first': 'Aris Kwong Sheng', 'middle': '', 'last': 'Diego',
    }


def test_adviser_supports_multiple_first_names_initials_and_particle_surname():
    lines = [
        "Ruth G. Luciano, PhD    Alvin James DC. Dela Cruz, MSIT",
        "Course Teacher          Adviser",
    ]

    assert _parse_adviser_from_approval(lines) == {
        "first": "Alvin James",
        "middle": "DC.",
        "last": "Dela Cruz",
    }


@pytest.mark.parametrize('names,labels,last', [
    ('RUTH ANN G. SANTOS, MSIT RACQUEL L. PULA, DIT', 'Capstone Instructor Capstone Adviser', 'Pula'),
    ('EMILSA T. BANTUG, MIT HENRY T. ROQUE, MSIT', 'Adviser Instructor', 'Bantug'),
    ('VANESSA C. PASCUAL,MSIT ROSALIE B. SISON,MSIT', 'Adviser Instructor', 'Pascual'),
    ('ROSALIE B. SISON, MSIT', 'Adviser & Instructor', 'Sison'),
])
def test_dataset_approval_column_order(names, labels, last):
    assert _parse_adviser_from_approval([names, '____________________', labels])['last'] == last


@pytest.mark.parametrize('mention,last', [
    ('We thank Mr. Ronaldin V. Bauat, our capstone adviser. Thank you for guiding us.', 'Bauat'),
    ('Our capstone adviser, Mr. Marcelino C. Collado Jr., who guided us.', 'Collado Jr.'),
    ('To our Capstone Adviser, Mr. Jefrain M. Padre, for his guidance.', 'Padre'),
])
def test_dataset_explicit_adviser_mentions(mention, last):
    assert _parse_adviser_mention(mention)['last'] == last


def test_adviser_never_uses_acknowledgement_prose_as_a_name():
    assert _parse_adviser_from_approval(['A heartfelt thanks for the commitment from', 'their capstone adviser']) is None
    assert _parse_adviser_mention('Our adviser helped us complete the project.') is None


def test_cover_natural_names_and_submitted_by_marker():
    natural = ['By:', 'LARS NEILSON R. ALMIROL', 'LAURA A. CELEDON',
               'CLYDE VINCENT V. MARTINEZ', 'PAUL JOHN V. NICOLAS', 'DECEMBER 2025']
    assert [person['last'] for person in _parse_cover_authors(natural)] == ['Almirol', 'Celedon', 'Martinez', 'Nicolas']
    assert _parse_cover_authors(['Submitted By:', 'Dela Cruz, Kirby C.', 'BSIT - 4H'])[0]['last'] == 'Dela Cruz'


def test_cover_trailing_commas_and_five_members_excludes_instructor():
    lines = ['by:', 'MANUCOT, CHRISTOPHER JOHN M.,', 'PANGILINAN, RIA LYKA C.,',
             'PINEDA, EDMAR,', 'SAGNIT, AARON BENEDICT E.', 'DELA CRUZ, KIRBY C.',
             'Submitted to:', 'RUTH ANN G. SANTOS', 'DECEMBER 2025']
    authors = _parse_cover_authors(lines)
    assert len(authors) == 5
    assert authors[0] == {'first': 'Christopher John', 'middle': 'M.', 'last': 'Manucot'}
