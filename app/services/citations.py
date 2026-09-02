"""Plain-text academic citation exports for archived capstones."""
import re
import unicodedata


INSTITUTION = "Nueva Ecija University of Science and Technology"
SUPPORTED_FORMATS = {
    "apa": ("txt", "text/plain"),
    "bibtex": ("bib", "application/x-bibtex"),
    "ris": ("ris", "application/x-research-info-systems"),
}


def _value(record, key, default=""):
    value = record.get(key, default)
    return str(value).strip() if value is not None else default


def _author_name(author):
    return " ".join(filter(None, (
        _value(author, "aut_first_name"),
        _value(author, "aut_middle_name"),
        _value(author, "aut_last_name"),
    )))


def _apa_author(author):
    last = _value(author, "aut_last_name") or "Unknown Author"
    initials = [
        f"{name[0]}."
        for name in (
            _value(author, "aut_first_name"),
            _value(author, "aut_middle_name"),
        )
        if name
    ]
    return f"{last}, {' '.join(initials)}".rstrip()


def _apa_authors(authors):
    names = [_apa_author(author) for author in authors]
    if not names:
        return "Unknown Author"
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]}, & {names[1]}"
    return f"{', '.join(names[:-1])}, & {names[-1]}"


def _bibtex_escape(value):
    escapes = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
    }
    return "".join(escapes.get(char, char) for char in str(value))


def _citation_key(capstone, authors):
    lead = _value(authors[0], "aut_last_name") if authors else "capstone"
    normalized = unicodedata.normalize("NFKD", lead).encode("ascii", "ignore").decode()
    lead_key = re.sub(r"[^A-Za-z0-9]", "", normalized) or "capstone"
    year = re.sub(r"\D", "", _value(capstone, "capstone_year")) or "nd"
    capstone_id = re.sub(r"\D", "", _value(capstone, "capstone_id"))
    return f"{lead_key}{year}{capstone_id}"


def format_citation(capstone, authors, format_name="apa"):
    format_name = (format_name or "apa").lower()
    if format_name not in SUPPORTED_FORMATS:
        raise ValueError("Unsupported citation format.")

    title = _value(capstone, "capstone_title") or "Untitled capstone"
    year = _value(capstone, "capstone_year") or "n.d."
    program = _value(capstone, "program_name") or "Unknown program"

    if format_name == "apa":
        return (
            f"{_apa_authors(authors)} ({year}). {title} "
            f"[Unpublished capstone project]. {program}, {INSTITUTION}."
        )

    if format_name == "bibtex":
        author_text = " and ".join(_author_name(author) for author in authors) or "Unknown Author"
        return "\n".join((
            f"@mastersthesis{{{_citation_key(capstone, authors)},",
            f"  author = {{{_bibtex_escape(author_text)}}},",
            f"  title = {{{_bibtex_escape(title)}}},",
            f"  school = {{{_bibtex_escape(INSTITUTION)}}},",
            f"  year = {{{_bibtex_escape(year)}}},",
            f"  type = {{Unpublished capstone project}},",
            f"  note = {{Program: {_bibtex_escape(program)}}}",
            "}",
        ))

    lines = ["TY  - THES"]
    if authors:
        for author in authors:
            last = _value(author, "aut_last_name")
            given = " ".join(filter(None, (
                _value(author, "aut_first_name"),
                _value(author, "aut_middle_name"),
            )))
            lines.append(f"AU  - {last}, {given}".rstrip(", "))
    else:
        lines.append("AU  - Unknown Author")
    lines.extend((
        f"TI  - {title}",
        f"PY  - {year}",
        f"PB  - {INSTITUTION}",
        "M3  - Unpublished capstone project",
        f"N1  - Program: {program}",
        "ER  -",
    ))
    return "\r\n".join(lines) + "\r\n"


def citation_download_metadata(capstone, format_name):
    extension, mimetype = SUPPORTED_FORMATS[format_name]
    title = _value(capstone, "capstone_title") or "capstone"
    normalized = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", normalized).strip("-").lower()[:60] or "capstone"
    return f"{slug}.{extension}", mimetype
