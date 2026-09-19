from app.services.citations import citation_download_metadata, format_citation


CAPSTONE = {
    "capstone_id": 42,
    "capstone_title": "Research & Development",
    "capstone_year": 2026,
    "program_name": "BS Information Technology",
}
AUTHORS = [
    {"aut_first_name": "Amy", "aut_middle_name": "Q", "aut_last_name": "Sapin"},
    {"aut_first_name": "John", "aut_middle_name": "", "aut_last_name": "Doe"},
]


def test_apa_citation_has_authors_and_institution():
    citation = format_citation(CAPSTONE, AUTHORS, "apa")

    assert "Sapin, A. Q., & Doe, J." in citation
    assert "Nueva Ecija University of Science and Technology" in citation


def test_bibtex_escapes_reserved_characters():
    citation = format_citation(CAPSTONE, AUTHORS, "bibtex")

    assert citation.startswith("@mastersthesis{Sapin202642,")
    assert "Research \\& Development" in citation


def test_ris_and_download_metadata():
    citation = format_citation(CAPSTONE, AUTHORS, "ris")
    filename, mimetype = citation_download_metadata(CAPSTONE, "ris")

    assert "TY  - THES\r\n" in citation
    assert "AU  - Sapin, Amy Q\r\n" in citation
    assert filename == "research-development.ris"
    assert mimetype == "application/x-research-info-systems"
