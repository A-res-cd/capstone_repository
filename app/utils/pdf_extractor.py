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

    data = extract_capstone_data("instance/uploads/manuscripts/thesis.pdf")
    # data is a dict — see return value of extract_capstone_data() below.

Dependencies:
    pip install pdfplumber yake
"""

import re
import logging
import pdfplumber

logger = logging.getLogger(__name__)

try:
    import yake as _yake
    _YAKE_AVAILABLE = True
except ImportError:
    _YAKE_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _extract_page_text(page) -> str:
    """Retry tightly spaced PDF text with lower tolerance when words merge."""
    text = page.extract_text() or ""
    word_count = len(text.split())
    if word_count < 8 or len(text) / word_count < 8:
        return text

    recovered = page.extract_text(x_tolerance=0.5) or ""
    if len(recovered.split()) > word_count * 1.05:
        return recovered
    return text


def _parse_abstract_page(pages):
    """
    Returns (page_number, abstract_text) for the actual Abstract page.
    Ignores the Table of Contents.
    """
    toc_found = False

    for page_num, page in enumerate(pages, start=1):
        text = _extract_page_text(page)

        # Detect the Table of Contents page
        if not toc_found and re.search(r"TABLE\s*OF\s*CONTENTS", text, re.IGNORECASE):
            toc_found = True
            continue

        # Don't look for ABSTRACT until after the TOC
        if not toc_found:
            continue

        lines = text.splitlines()

        for i, line in enumerate(lines):
            if re.fullmatch(r"\s*ABSTRACT\s*", line, re.IGNORECASE):
                abstract = "\n".join(lines[i + 1:]).strip()
                return page_num, abstract

    return None, ""


def extract_abstract_text(pdf_path: str) -> str:
    """Extract only the manuscript's abstract body."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            _, abstract_text = _parse_abstract_page(pdf.pages)
        return abstract_text
    except Exception as exc:
        logger.error("Could not extract abstract text: %s", exc)
        return ""



_MIDDLE_INITIAL_PATTERN = re.compile(r"(?:[A-Za-z]\.){1,3}|[A-Za-z]{1,3}\.|[A-Za-z]", re.IGNORECASE)
_SURNAME_PARTICLES = {
    "da", "das", "de", "del", "dela", "della", "di", "do", "dos",
    "du", "la", "las", "los", "san", "santa", "van", "von",
}


def _format_name_token(token: str) -> str:
    return token.upper() if _MIDDLE_INITIAL_PATTERN.fullmatch(token) else token.title()


def _split_given_names(parts: list[str]) -> tuple[str, str]:
    """Treat trailing dotted initials as middle names; keep other words as first names."""
    middle_start = len(parts)
    while middle_start > 0 and _MIDDLE_INITIAL_PATTERN.fullmatch(parts[middle_start - 1]):
        middle_start -= 1

    first = " ".join(_format_name_token(part) for part in parts[:middle_start])
    middle = " ".join(_format_name_token(part) for part in parts[middle_start:])
    return first, middle


def _parse_name_string(raw: str) -> dict | None:
    """
    Parse 'LAST, FIRST [MIDDLE_WORDS...]' (all-caps, cover-page format)
    into a name dict.

    Examples handled:
      INDIANA, CHRISTONI G.      -> first=Christoni, middle=G.,         last=Indiana
      MADULID, ADRIAN MILES R.   -> first=Adrian Miles, middle=R.,  last=Madulid
      DELA CRUZ, ALVIN JAMES DC. -> first=Alvin James, middle=DC., last=Dela Cruz
      OLMO, ELMARK JOSH          -> first=Elmark, middle=Josh,     last=Olmo
    """
    raw = raw.strip()
    if ',' not in raw:
        return None
    last_part, rest = raw.split(',', 1)
    given_parts = rest.strip().split()
    if not last_part.strip() or not rest.strip():
        return None

    # Some cover pages separate first and middle names with a second comma.
    if ',' in rest:
        first_parts, middle_part = rest.split(',', 1)
        first = ' '.join(_format_name_token(part) for part in first_parts.split())
        middle = ' '.join(_format_name_token(part) for part in middle_part.split())
    else:
        first, middle = _split_given_names(given_parts)
        # In LAST, FIRST MIDDLE format, a full middle name has no initial
        # punctuation. Treat remaining words as middle when no initial exists.
        if not middle and len(given_parts) > 1:
            first = _format_name_token(given_parts[0])
            middle = ' '.join(_format_name_token(part) for part in given_parts[1:])
    if not first:
        return None
    logger.debug("Parsing name string: %s -> last='%s', given_parts=%s", raw, last_part, given_parts)
    return {
        'first': first,
        'middle': middle,
        'last': ' '.join(_format_name_token(part) for part in last_part.split()),
    }


def _parse_natural_name(raw: str) -> dict | None:
    """Parse FIRST [MIDDLE_INITIALS] LAST, including particle surnames."""
    words = raw.strip().split()
    if len(words) < 2:
        return None

    surname_start = len(words) - 1
    while surname_start > 0 and words[surname_start - 1].lower().rstrip('.') in _SURNAME_PARTICLES:
        surname_start -= 1
    if surname_start == 0:
        return None

    first, middle = _split_given_names(words[:surname_start])
    return {
        'first': first,
        'middle': middle,
        'last': ' '.join(_format_name_token(part) for part in words[surname_start:]),
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

            parsed = _parse_natural_name(adviser_raw)
            if parsed:
                logger.debug("Parsed adviser name: %s -> %s", adviser_raw, parsed)
                return parsed
    logger.debug("No adviser found in approval sheet lines.")
    return None

def _suggest_keywords_yake(text: str, top_n: int = 6) -> list[str]:
    """
    Suggest up to six topic keywords, favoring phrases tied to the manuscript title.
    Returns an empty list if yake isn't installed.
    """
    if not _YAKE_AVAILABLE or not text.strip() or top_n <= 0:
        return []
    top_n = min(top_n, 6)
    import yake

    title, separator, _ = text.partition('\n')
    candidate_limit = max(24, top_n * 4)

    def extract(source: str, limit: int) -> list[tuple[str, float]]:
        if not source.strip():
            return []
        extractor = yake.KeywordExtractor(
            lan='en', n=3, dedupLim=0.7, top=limit, features=None
        )
        return extractor.extract_keywords(source)

    results = extract(text, candidate_limit)
    title_results = extract(title, candidate_limit) if separator else []
    title_tokens = set(re.findall(r"[a-z0-9]+", title.lower()))

    # Keep the best YAKE score for each phrase, and mark title-derived phrases
    # so they win ties against broad abstract terms.
    candidates = {}
    for phrase, score in results:
        key = phrase.casefold().strip()
        if key:
            candidates[key] = [phrase, score, False]
    for phrase, score in title_results:
        key = phrase.casefold().strip()
        if key:
            current = candidates.get(key)
            if current is None or score < current[1]:
                candidates[key] = [phrase, score, True]
            else:
                current[2] = True

    ranked = []
    for phrase, score, from_title in candidates.values():
        tokens = set(re.findall(r"[a-z0-9]+", phrase.lower()))
        overlap = len(tokens & title_tokens)
        relevance = overlap / len(tokens) if tokens else 0
        ranked.append((-relevance, -overlap, not from_title, score, phrase))

    ranked.sort()
    selected = []
    selected_token_sets = []
    for _relevance, _overlap, _not_title, _score, phrase in ranked:
        tokens = set(re.findall(r"[a-z0-9]+", phrase.lower()))
        # Avoid filling the six slots with minor variations of one phrase.
        if any(tokens and (tokens <= prior or prior <= tokens) for prior in selected_token_sets):
            continue
        selected.append(phrase)
        selected_token_sets.append(tokens)
        if len(selected) >= top_n:
            break

    logger.debug("YAKE extracted title-aware keywords: %s", selected)
    return selected


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
        'abstract_text':  '',
    }

    try:
        with pdfplumber.open(pdf_path) as pdf:

            # ── Page 1: Cover ─────────────────────────────────────
            p1_text  = _extract_page_text(pdf.pages[0])
            p1_lines = [l.strip() for l in p1_text.splitlines() if l.strip()]

            # Title: all lines before "A CAPSTONE AND RESEARCH PROJECT"
            title_lines = []
            for line in p1_lines:
                if re.match(r'^A CAPSTONE', line, re.IGNORECASE):
                    break
                title_lines.append(line)
            if title_lines:
                result['title'] = ' '.join(title_lines)

            # Prefer the cover's month/year date; otherwise use its last year.
            month_names = (
                r'JAN(?:UARY)?|FEB(?:RUARY)?|MAR(?:CH)?|APR(?:IL)?|MAY|'
                r'JUN(?:E)?|JUL(?:Y)?|AUG(?:UST)?|SEP(?:TEMBER)?|'
                r'OCT(?:OBER)?|NOV(?:EMBER)?|DEC(?:EMBER)?'
            )
            dated_years = re.findall(
                rf'\b(?:{month_names})\.?\s+(20\d{{2}})\b', p1_text, re.IGNORECASE
            )
            year_matches = re.findall(r'\b(20\d{2})\b', p1_text)
            if dated_years or year_matches:
                result['year'] = int((dated_years or year_matches)[-1])

            # Authors: lines between "by:" and the date line (e.g. "DECEMBER 2025")
            in_authors = False
            for line in p1_lines:
                if re.fullmatch(r'by\s*:?', line, re.IGNORECASE):
                    in_authors = True
                    continue
                if in_authors:
                    if re.match(r'^[A-Z]+\s+\d{4}$', line):
                        break
                    # Cover authors may be printed in side-by-side columns.
                    for author_line in re.split(r'\s{2,}', line):
                        parsed = _parse_name_string(author_line)
                        if parsed:
                            result['authors'].append(parsed)

            # ── Page 3: Approval Sheet ────────────────────────────
            p3_lines = [
                l.strip()
                for l in _extract_page_text(pdf.pages[2]).splitlines()
                if l.strip()
            ] if len(pdf.pages) > 2 else []
            result['adviser'] = _parse_adviser_from_approval(p3_lines)

            # ── Abstract page: scan all pages ─────────────────────
            abstract_page, abstract_full_text = _parse_abstract_page(pdf.pages)
            result['abstract_page'] = abstract_page
            result['abstract_text'] = abstract_full_text


            # Use topic-bearing text rather than front matter or references.
            topic_text = '\n'.join(filter(None, [result['title'], abstract_full_text]))
            result['keywords'] = _suggest_keywords_yake(topic_text)

    except Exception as exc:
        # Return whatever was collected before the error; never crash the route
        logger.error("Could not fully extract capstone PDF: %s", exc)
        result['_error'] = "Could not fully extract metadata from this PDF."
    logger.debug("Capstone extraction completed with fields: %s", sorted(result))
    return result
    
