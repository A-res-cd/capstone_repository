"""
app/services/recommender.py

Content-based topic-similarity recommender.

Purpose: when a student proposes a new capstone title/topic, check it
against every existing (non-archived) capstone's title + keywords and
surface the closest matches — so duplicate or near-duplicate proposals
get caught before they reach an adviser.

Approach: classic TF-IDF vectorization + cosine similarity, implemented
in pure Python (no numpy/scikit-learn dependency — the corpus size for a
single department's repository is small enough that this stays fast).

Usage:
    from app.services.recommender import TopicRecommender

    corpus = get_capstones_corpus()   # [{capstone_id, capstone_title, capstone_keywords}, ...]
    engine = TopicRecommender(corpus)
    matches = engine.find_similar("AI-powered attendance tracker", "facial recognition, attendance")
    # -> [{"capstone_id": 12, "capstone_title": "...", "similarity": 0.62}, ...]
"""

import math
import re
from collections import Counter

# Common English stopwords worth stripping so they don't dilute the
# similarity score. Kept short and deliberately non-exhaustive — this is
# a heuristic filter, not a linguistics project.
_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "for", "to", "in", "on", "with",
    "using", "based", "system", "app", "application", "study", "analysis",
    "development", "design", "implementation", "towards", "via", "a.i",
    "is", "are", "as", "by", "its", "into", "through",
}

_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z\-]+")


def _tokenize(text):
    if not text:
        return []
    tokens = _TOKEN_RE.findall(text.lower())
    return [t for t in tokens if t not in _STOPWORDS and len(t) > 2]


def _text_for_record(record):
    """Combine title + keywords into one bag-of-words source string."""
    title = record.get("capstone_title") or ""
    keywords = record.get("capstone_keywords") or ""
    # Title words count once; keyword words are repeated so they carry a
    # bit more weight (keywords are hand-picked, so a match there is a
    # stronger topical signal than an incidental title word).
    return f"{title} {keywords} {keywords}"


class TopicRecommender:
    def __init__(self, corpus):
        """
        corpus: list of dicts, each with at least
                capstone_id, capstone_title, capstone_keywords
        """
        self.records = corpus
        self.doc_tokens = [_tokenize(_text_for_record(r)) for r in corpus]
        self._df = self._build_document_frequencies()
        self._doc_vectors = [
            self._vectorize(tokens) for tokens in self.doc_tokens
        ]

    def _build_document_frequencies(self):
        df = Counter()
        for tokens in self.doc_tokens:
            for term in set(tokens):
                df[term] += 1
        return df

    def _idf(self, term):
        n = len(self.doc_tokens) or 1
        # +1 smoothing so unseen query terms don't blow up to infinity
        df = self._df.get(term, 0)
        return math.log((n + 1) / (df + 1)) + 1

    def _vectorize(self, tokens):
        if not tokens:
            return {}
        tf = Counter(tokens)
        length = len(tokens)
        vec = {term: (count / length) * self._idf(term) for term, count in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {term: v / norm for term, v in vec.items()}

    @staticmethod
    def _cosine(vec_a, vec_b):
        if not vec_a or not vec_b:
            return 0.0
        # iterate the shorter vector for speed
        if len(vec_a) > len(vec_b):
            vec_a, vec_b = vec_b, vec_a
        return sum(w * vec_b.get(term, 0.0) for term, w in vec_a.items())

    def find_similar(self, query_title, query_keywords="", top_n=5, min_score=0.12):
        """
        Returns the top_n most similar existing capstones to the given
        proposed title/keywords, sorted highest similarity first.
        Scores below min_score are dropped as noise.
        """
        query_tokens = _tokenize(f"{query_title} {query_keywords} {query_keywords}")
        query_vec = self._vectorize(query_tokens)

        scored = []
        for record, doc_vec in zip(self.records, self._doc_vectors):
            score = self._cosine(query_vec, doc_vec)
            if score >= min_score:
                scored.append({
                    "capstone_id": record.get("capstone_id"),
                    "capstone_title": record.get("capstone_title"),
                    "capstone_keywords": record.get("capstone_keywords") or "",
                    "specialization_name": record.get("specialization_name") or "",
                    "similarity": round(score, 3),
                })

        scored.sort(key=lambda r: r["similarity"], reverse=True)
        return scored[:top_n]
