from importlib import import_module

import pytest
from flask import Flask, g, session

from app.services.recommender import TopicRecommender


pages_module = import_module("app.routes.pages")


CORPUS = [
    {"capstone_id": 1, "capstone_title": "Weather Sensor Sensor"},
    {"capstone_id": 2, "capstone_title": "Orchard Sensor Sensor"},
    {"capstone_id": 3, "capstone_title": "Weather Gateway"},
]


def test_exact_and_reordered_titles_match():
    engine = TopicRecommender(CORPUS)
    for title in ("Weather Sensor Sensor", "SENSOR, weather sensor!"):
        match = engine.find_similar(title)[0]
        assert match["capstone_id"] == 1
        assert match["similarity"] == 1.0


def test_keywords_and_abstracts_do_not_affect_scores():
    with_metadata = [
        {**record, "capstone_keywords": "orchard weather " * 20, "abstract": "orchard " * 50}
        for record in CORPUS
    ]
    expected = TopicRecommender(CORPUS).find_similar("orchard weather")
    assert TopicRecommender(with_metadata).find_similar("orchard weather") == expected


def test_empty_short_unrelated_and_missing_titles_are_safe():
    engine = TopicRecommender(CORPUS + [{"capstone_id": 4, "capstone_title": None}])
    for title in ("", "AI", "the and for", "Marine Conservation"):
        assert engine.find_similar(title) == []
    assert TopicRecommender([]).find_similar("Weather Sensor") == []


def test_repeated_title_words_affect_tfidf_scores():
    corpus = [{"capstone_id": 1, "capstone_title": "Orchard Weather Weather"}]
    match = TopicRecommender(corpus).find_similar("Orchard Orchard Weather")[0]
    assert match["similarity"] == 0.8


def test_tfidf_weights_rare_title_terms():
    tfidf_matches = TopicRecommender(CORPUS).find_similar("orchard weather")
    tfidf_scores = {match["capstone_id"]: match["similarity"] for match in tfidf_matches}
    assert tfidf_scores[2] > tfidf_scores[1]


def test_results_are_ranked_limited_and_bounded():
    corpus = [
        {"capstone_id": index, "capstone_title": "Weather Sensor " + "Gateway " * index}
        for index in range(8)
    ]
    matches = TopicRecommender(corpus).find_similar("Weather Sensor")
    scores = [match["similarity"] for match in matches]
    assert len(matches) == 5
    assert scores == sorted(scores, reverse=True)
    assert all(0.12 <= score <= 1.0 for score in scores)


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY="title-similarity-test")
    app.register_blueprint(pages_module.pages)
    app.add_url_rule("/signin", "auth.signin", lambda: "Sign in")
    app.add_url_rule("/", "main.home", lambda: "Home")

    @app.before_request
    def load_test_user():
        g.user = {"role_id": session.get("role_id", 1)} if session.get("user_id") else None

    monkeypatch.setattr(pages_module, "get_capstones_corpus", lambda: CORPUS)
    with app.test_client() as client:
        with client.session_transaction() as user_session:
            user_session["user_id"] = 7
        yield client


@pytest.mark.parametrize("legacy_fields", [
    {"mode": "tf"}, {"mode": []}, {"keywords": "gateway " * 50},
])
def test_api_uses_tfidf_and_ignores_legacy_fields(client, legacy_fields):
    payload = {"title": "Orchard Weather"}
    response = client.post("/api/topic-similarity", json=payload)
    assert response.status_code == 200
    assert response.json["matches"] == TopicRecommender(CORPUS).find_similar(payload["title"])
    assert client.post("/api/topic-similarity", json={**payload, **legacy_fields}).json == response.json


def test_api_handles_exact_and_short_titles(client):
    response = client.post("/api/topic-similarity", json={"title": "Weather Sensor Sensor"})
    assert response.json["matches"][0]["similarity"] == 1.0
    for title in ("", " AI "):
        assert client.post("/api/topic-similarity", json={"title": title}).json["matches"] == []


@pytest.mark.parametrize("payload", [
    [], ["weather"], {}, {"title": None}, {"title": 42}, {"title": ["weather"]},
    {"title": "x" * 256},
])
def test_api_rejects_invalid_inputs_without_querying_archive(client, monkeypatch, payload):
    def unexpected_query():
        pytest.fail("Invalid input must not query the archive")

    monkeypatch.setattr(pages_module, "get_capstones_corpus", unexpected_query)
    response = client.post("/api/topic-similarity", json=payload)
    assert response.status_code == 400
    assert response.json["error"]


def test_api_keeps_student_access_requirement(client):
    with client.session_transaction() as user_session:
        user_session["role_id"] = 2
    assert client.post("/api/topic-similarity", json={"title": "Weather"}).status_code == 302
    with client.session_transaction() as user_session:
        user_session.clear()
    assert client.post("/api/topic-similarity", json={"title": "Weather"}).headers["Location"] == "/signin"
