"""
app/utils/pdf_extractor.py

Extracts structured capstone metadata from a PDF file.

Designed for DLSUD/NEUST-format capstone manuscripts which follow a
consistent title page and approval sheet layout. Returns a dict of
extracted fields that pre-fill the Admin's "New Capstone" form.

All fields are best-effort — the Admin always reviews and edits before
saving. Nothing is written to the database by this module.

Usage:
    from app.utils.pdf_extractor import extract_capstone_data

    data = extract_capstone_data("app/static/uploads/thesis.pdf")
    # data is a dict — see return value of extract_capstone_data() below.

Dependencies:
    pip install pdfplumber yake
"""

import re
import pdfplumber

try:
    import yake as _yake
    _YAKE_AVAILABLE = True
except ImportError:
    _YAKE_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_name_string(raw: str) -> dict | None:
    """
    Parse 'LAST, FIRST [MIDDLE_WORDS...]' (all-caps, cover-page format)
    into a name dict.

    Examples handled:
      INDIANA, CHRISTONI G.     -> first=Christoni, middle=G.,         last=Indiana
      MADULID, ADRIAN MILES R.  -> first=Adrian,    middle=Miles R.,   last=Madulid
      MAGNO, HYUNG JIN KYLE A.  -> first=Hyung,     middle=Jin Kyle A.,last=Magno
      OLMO, ELMARK JOSH         -> first=Elmark,    middle=Josh,       last=Olmo
    """
    raw = raw.strip()
    if ',' not in raw:
        return None
    last_part, rest = raw.split(',', 1)
    given_parts = rest.strip().split()
    print(f"Parsing name string: {raw} -> last='{last_part}', given_parts={given_parts}")
    return {
        'first':  given_parts[0].title()                              if given_parts else '',
        'middle': ' '.join(p.title() for p in given_parts[1:])       if len(given_parts) > 1 else '',
        'last':   last_part.strip().title(),
    }


def _parse_adviser_from_approval(lines: list[str]) -> dict | None:
    """
    The approval sheet renders the course teacher and adviser names on
    the same extracted line due to two-column layout:

      'Ruth G. Luciano, PhD  Jodell R. Bulaclac, MSIT'
      'Course Teacher         Adviser'

    Finds the label line containing 'Adviser', looks one line up for the
    names, strips degree suffixes, then takes the right-hand name.
    """
    degree_pattern = re.compile(
        r',?\s*(Ph\.?D\.?|M\.?S\.?I\.?T\.?|MIT|DIT|MBusAn|Dr\.|PhD|MSIT)',
        re.IGNORECASE
    )

    for i, line in enumerate(lines):
        if re.search(r'\bAdviser\b', line, re.IGNORECASE) and i > 0:
            names_line = lines[i - 1]
            cleaned    = degree_pattern.sub('', names_line).strip()

            # Two names separated by 2+ spaces (from two-column layout)
            parts = re.split(r'\s{2,}', cleaned)
            adviser_raw = parts[-1].strip() if len(parts) >= 2 else ' '.join(cleaned.split()[len(cleaned.split())//2:])

            words = adviser_raw.strip().split()
            if len(words) >= 2:
                print(f"Parsed adviser name: {adviser_raw} -> {words}")
                return {
                    'first':  words[0],
                    'middle': ' '.join(words[1:-1]) if len(words) > 2 else '',
                    'last':   words[-1],
                }
    print("No adviser found in approval sheet lines.")
    return None

def _suggest_keywords_yake(text: str, top_n: int = 8) -> list[str]:
    """
    Fallback keyword extraction using YAKE when the PDF doesn't have an
    explicit 'Keywords:' line (or when you want to supplement it).
    Returns an empty list if yake isn't installed.
    """
    if not _YAKE_AVAILABLE or not text:
        return []
    import yake
    extractor = yake.KeywordExtractor(
        lan='en', n=3, dedupLim=0.7, top=top_n, features=None
    )
    results = extractor.extract_keywords(text)
    print(f"YAKE extracted keywords: {results}")
    return [phrase for phrase, _score in results]


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def extract_capstone_data(pdf_path: str) -> dict:
    result = {
        'title':          None,
        'year':           None,
        'program':        None,
        'specialization': None,
        'authors':        [],
        'adviser':        None,
        'keywords':       [],
        'abstract_page':  None,
    }

    try:
        with pdfplumber.open(pdf_path) as pdf:

            # ── Page 1: Cover ─────────────────────────────────────
            p1_text  = pdf.pages[0].extract_text() or ''
            p1_lines = [l.strip() for l in p1_text.splitlines() if l.strip()]

            # Title: all lines before "A CAPSTONE AND RESEARCH PROJECT"
            title_lines = []
            for line in p1_lines:
                if re.match(r'^A CAPSTONE', line, re.IGNORECASE):
                    break
                title_lines.append(line)
            if title_lines:
                result['title'] = ' '.join(title_lines)

            # Year: first 4-digit year that starts with 20
            year_match = re.search(r'\b(20\d{2})\b', p1_text)
            if year_match:
                result['year'] = int(year_match.group(1))

            # Authors: lines between "by:" and the date line (e.g. "DECEMBER 2025")
            in_authors = False
            for line in p1_lines:
                if line.lower() == 'by:':
                    in_authors = True
                    continue
                if in_authors:
                    if re.match(r'^[A-Z]+\s+\d{4}$', line):
                        break
                    parsed = _parse_name_string(line)
                    if parsed:
                        result['authors'].append(parsed)

            # ── Page 2: Title Page ────────────────────────────────
            p2_text = pdf.pages[1].extract_text() or ''

            # ── Page 3: Approval Sheet ────────────────────────────
            p3_lines = [
                l.strip()
                for l in (pdf.pages[2].extract_text() or '').splitlines()
                if l.strip()
            ]
            result['adviser'] = _parse_adviser_from_approval(p3_lines)

            # ── Abstract page: scan all pages ─────────────────────
            abstract_full_text = ''
            for i, page in enumerate(pdf.pages):
                t = page.extract_text() or ''
                if re.search(r'^\s*ABSTRACT\s*$', t, re.MULTILINE):
                    result['abstract_page'] = i + 1  # 1-based

                    # Keywords from explicit 'Keywords:' line
                    kw_match = re.search(r'Keywords?:?\s*(.+?)(?:\n\f|$)', t, re.DOTALL)
                    if kw_match:
                        kw_raw = kw_match.group(1).strip()
                        sep    = ';' if ';' in kw_raw else ','
                        result['keywords'] = [
                            k.strip().replace('\n', ' ')
                            for k in kw_raw.split(sep) if k.strip()
                        ]
                    abstract_full_text = t
                    break

            # YAKE fallback: if no explicit keywords line was found
            if not result['keywords'] and abstract_full_text:
                result['keywords'] = _suggest_keywords_yake(abstract_full_text, top_n=8)

    except Exception as exc:
        # Return whatever was collected before the error; never crash the route
        result['_error'] = str(exc)

    return result
