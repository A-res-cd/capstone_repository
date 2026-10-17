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


def _parse_abstract_page(pages, text_cache=None):
    """
    Returns (page_number, abstract_text) for the actual Abstract page.
    Ignores the Table of Contents.
    """
    for page_num, page in enumerate(pages, start=1):
        if text_cache is not None and page_num - 1 in text_cache:
            text = text_cache[page_num - 1]
        else:
            text = _extract_page_text(page)
            if text_cache is not None:
                text_cache[page_num - 1] = text

        # Detect the Table of Contents page
        if re.search(r"TABLE\s*OF\s*CONTENTS", text, re.IGNORECASE):
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
    if token.casefold().rstrip('.') in {'jr', 'sr'}:
        return token.capitalize()
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
    raw = raw.strip(' ,')
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
        # Preserve multiple first names; a single undotted trailing word may
        # be the full middle name in LAST, FIRST MIDDLE format.
        if not middle and len(given_parts) == 2:
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
    if words[-1].rstrip('.').casefold() in {'jr', 'sr', 'ii', 'iii', 'iv'}:
        surname_start -= 1
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


_DEGREE_PATTERN = re.compile(r',?\s*\b(?:Ph\.?D\.?|M\.?S\.?I\.?T\.?|MIT|DIT|MBusAn|MSc)\b\.?', re.I)
_PERSON_NOISE = {'the', 'our', 'their', 'for', 'from', 'thanks', 'project', 'research',
                 'capstone', 'instructor', 'teacher', 'adviser', 'advisor', 'date', 'approved'}


def _clean_person_name(raw: str) -> dict | None:
    raw = re.sub(r'^(?:Dr|Mr|Mrs|Ms|Prof)\.?\s+', '', raw.strip(), flags=re.I)
    raw = _DEGREE_PATTERN.sub('', raw).strip(' ,_')
    raw = re.sub(r'([a-z])([A-Z]\.)', r'\1 \2', raw)
    raw = re.sub(r'(?<=\.)(?=[A-Za-z]{2})', ' ', raw)
    tokens = raw.split()
    if (not 2 <= len(tokens) <= 8 or set(word.casefold().strip('.,') for word in tokens) & _PERSON_NOISE
            or not re.fullmatch(r"[^\W\d_](?:[^\W\d_]|[.,'’\s-])*", raw)):
        return None
    return _parse_name_string(raw) if ',' in raw else _parse_natural_name(raw)


def _parse_cover_authors(lines: list[str]) -> list[dict]:
    candidates = []
    in_authors = False
    for line in lines:
        if re.fullmatch(r'(?:submitted\s+)?by\s*:?\s*', line, re.I):
            in_authors = True
            continue
        if not in_authors:
            continue
        if (re.search(r'\d{4}|\b(?:BSIT|BSDS|submitted|instructor|advis[eo]r)\b', line, re.I)
                or re.match(r'^(?:January|February|March|April|May|June|July|August|September|October|November|December)\b', line, re.I)):
            break
        candidates.extend(re.split(r'\s{2,}', line))
    surname_first = sum(',' in line for line in candidates) >= len(candidates) / 2
    authors = []
    seen = set()
    for raw in candidates:
        if surname_first and ',' not in raw and len(raw.split()) > 1:
            last, rest = raw.split(None, 1)
            raw = f'{last}, {rest}'
        person = _clean_person_name(raw)
        if person:
            key = tuple(value.casefold() for value in person.values())
            if key not in seen:
                authors.append(person)
                seen.add(key)
    return authors


def _parse_adviser_from_approval(lines: list[str]) -> dict | None:
    """
    The approval sheet renders the course teacher and adviser names on
    the same extracted line due to two-column layout:

      'Ruth G. Luciano, PhD  Jodell R. Bulaclac, MSIT'
      'Course Teacher         Adviser'

    Match role order to name columns, supporting either adviser position.
    Skip signature rules and degree suffixes without guessing from prose.
    """
    for i, line in enumerate(lines):
        if not re.search(r'\bAdvis[eo]r\b', line, re.I):
            continue
        inline = re.match(r'^\s*(?:Capstone\s+|Research\s+)?Advis[eo]r\s*:\s*(.+)', line, re.I)
        if inline:
            parsed = _clean_person_name(inline.group(1))
            if parsed:
                return parsed
        labels = re.findall(r'\b(?:Advis[eo]r|(?:Course\s+|Capstone\s+)?Teacher|(?:Capstone\s+)?Instructor)\b', line, re.I)
        # Only role-only lines may select an adjacent signature; prose is not a name.
        if re.sub(r'\b(?:Advis[eo]r|Teacher|Instructor|Course|Capstone|Research)\b|[\s&/,:-]', '', line, flags=re.I):
            continue
        column = next((n for n, role in enumerate(labels) if re.fullmatch(r'Advis[eo]r', role, re.I)), 0)
        for names_line in reversed(lines[max(0, i - 3):i]):
            if not re.search(r'[^\W\d_]', names_line):
                continue
            parts = [part.strip(' ,') for part in _DEGREE_PATTERN.split(names_line) if part.strip(' ,')]
            if len(parts) == 1:
                parts = re.split(r'\s{2,}', parts[0])
            if column < len(parts):
                parsed = _clean_person_name(parts[column])
                if parsed:
                    return parsed
    logger.debug("No adviser found in approval sheet lines.")
    return None


def _parse_adviser_mention(text: str) -> dict | None:
    """Fallback only to an explicitly named adviser in front-matter prose."""
    text = re.sub(r'\s+', ' ', text)
    name = r"([^\W\d_](?:[^\W\d_]|[.'’-])*(?:\s+[^\W\d_](?:[^\W\d_]|[.'’-])*){1,7}?)"
    patterns = [
        r'\badvis[eo]r\s*[, :]\s*(?:(?:Dr|Mr|Mrs|Ms|Prof)\.?\s+)?' + name + r'(?=,|\s+(?:who|for|and our)\b)',
        r'\b(?:Dr|Mr|Mrs|Ms|Prof)\.?\s+' + name + r',\s*(?:our\s+|the researchers[’\x27]\s+)?(?:capstone\s+|research\s+)?advis[eo]r\b',
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.I):
            person = _clean_person_name(match.group(1))
            if person:
                return person
    return None

_TOPIC_PHRASES = (
    # Topic patterns represented by datasets/wst, datasets/dst and datasets/nst.
    'records management', 'record management', 'student profile', 'academic information',
    'scholarship application', 'incident reporting', 'infrastructure issues', 'faculty evaluation',
    'career readiness', 'smart farming', 'data logger', 'automated misting', 'lettuce cultivation',
    'stock monitoring', 'point of sales', 'e-commerce', 'guest monitoring', 'reservation',
    'dispatching', 'trucking services', 'wireless local area network', 'wireless bridge connection',
    'wired network infrastructure', 'wireless network', 'bandwidth management', 'parental controls',
    'internet connectivity', 'network expansion', 'router deployment', 'access point',
    'cat6 ethernet cable', 'centralized internet infrastructure', 'wireless connectivity',
    'soil moisture', 'irrigation monitoring', 'feedback', 'complaint', 'child-at-risk',
    'inventory management', 'information management', 'record and monitoring', 'internet sharing',
)
_KEYWORD_NOISE = {'a', 'an', 'and', 'the', 'of', 'for', 'to', 'in', 'at', 'with', 'using',
                  'by', 'on', 'based', 'web', 'design', 'development', 'implementation',
                  'system', 'systems', 'study', 'research', 'project', 'capstone', 'abstract',
                  'results', 'respondents', 'researchers', 'proposed', 'developed',
                  'implementing', 'enhancing', 'front', 'page', 'platform',
                  'spiral', 'model', 'life', 'cycle', 'sdlc', 'likert', 'respondent',
                  'statistical', 'validation', 'acceptance', 'testing', 'methodology',
                  'aim', 'aims', 'aimed', 'support', 'enhance', 'improve', 'improving',
                  'strengthening', 'optimizing', 'expanding', 'fortifying', 'this', 'that'}
_INSTITUTION_WORDS = {'neust', 'university', 'school', 'highschool', 'college', 'barangay',
                      'city', 'government', 'museo', 'museum', 'station', 'hall', 'center', 'hostel',
                      'institution', 'institutions', 'heis'}


def _topic_tokens(phrase):
    variants = {'records': 'record', 'profiles': 'profile', 'applications': 'application',
                'networks': 'network', 'services': 'service', 'routers': 'router',
                'connections': 'connection'}
    return {variants.get(word, word) for word in re.findall(r'[a-z0-9]+', phrase.lower())} - _KEYWORD_NOISE


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
    title_tokens = _topic_tokens(title)

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

    domain_phrases = set()
    for template in _TOPIC_PHRASES:
        pattern = r'\b' + re.escape(template).replace(r'\ ', r'[\s-]+') + r'\b'
        if template in {'feedback', 'complaint'} and not re.search(pattern, title, re.I):
            continue
        match = re.search(pattern, text, re.I)
        if match:
            phrase = ' '.join(match.group(0).split())
            key = phrase.casefold()
            domain_phrases.add(key)
            if key not in candidates:
                candidates[key] = [phrase, 1.0, bool(re.search(pattern, title, re.I))]

    location_tokens = set()
    domain_tokens = set().union(*(_topic_tokens(phrase) for phrase in domain_phrases)) if domain_phrases else set()
    for location in re.finditer(r'\b(?:at|for|in|of)\s+(.+?)(?=\b(?:using|to|with)\b|$)', title, re.I):
        tokens = _topic_tokens(location.group(1))
        if tokens & _INSTITUTION_WORDS:
            location_tokens.update(tokens - domain_tokens)

    ranked = []
    for phrase, score, from_title in candidates.values():
        tokens = _topic_tokens(phrase)
        domain = phrase.casefold() in domain_phrases
        if (not tokens or (not domain and (len(tokens) == 1
                or tokens & (_INSTITUTION_WORDS | location_tokens)))):
            continue
        overlap = len(tokens & title_tokens)
        if not domain and not overlap:
            continue
        relevance = overlap / len(tokens) if tokens else 0
        # Prefer topic-bearing phrases over school/location names or methodology.
        topic_score = (10 * domain + 3 * relevance + 0.5 * overlap
                       + 0.5 * from_title + 0.5 / (1 + score))
        ranked.append((-topic_score, -overlap, not from_title, score, phrase))

    ranked.sort()
    selected = []
    selected_token_sets = []
    for _relevance, _overlap, _not_title, _score, phrase in ranked:
        tokens = _topic_tokens(phrase)
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
            text_cache = {}
            def page_text(index):
                if index not in text_cache:
                    text_cache[index] = _extract_page_text(pdf.pages[index])
                return text_cache[index]

            p1_text  = page_text(0)
            p1_lines = [l.strip() for l in p1_text.splitlines() if l.strip()]

            # Title: all lines before "A CAPSTONE AND RESEARCH PROJECT"
            title_lines = []
            for line in p1_lines:
                if re.match(r'^(?:A\s*CAPSTONE|An\s+Undergraduate)', line, re.IGNORECASE):
                    break
                if line.upper() == 'FRONT PAGE':
                    continue
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
            result['authors'] = _parse_cover_authors(p1_lines)

            # ── Page 3: Approval Sheet ────────────────────────────
            front_matter = []
            for index in range(min(8, len(pdf.pages))):
                text = page_text(index)
                front_matter.append(text)
                result['adviser'] = _parse_adviser_from_approval([line.strip() for line in text.splitlines() if line.strip()])
                if result['adviser']:
                    break
            if not result['adviser']:
                result['adviser'] = _parse_adviser_mention(' '.join(front_matter))

            # ── Abstract page: scan all pages ─────────────────────
            abstract_page, abstract_full_text = _parse_abstract_page(pdf.pages, text_cache)
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
    
