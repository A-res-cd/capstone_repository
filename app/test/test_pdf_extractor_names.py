from app.utils.pdf_extractor import _parse_adviser_from_approval, _parse_name_string


def test_author_supports_multiple_first_names_initials_and_particle_surname():
    assert _parse_name_string("DELA CRUZ, ALVIN JAMES DC.") == {
        "first": "Alvin James",
        "middle": "DC.",
        "last": "Dela Cruz",
    }


def test_author_keeps_second_given_name_without_middle_initial():
    assert _parse_name_string("OLMO, ELMARK JOSH") == {
        "first": "Elmark Josh",
        "middle": "",
        "last": "Olmo",
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
