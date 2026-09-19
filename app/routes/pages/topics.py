"""Pages topics routes and local helpers."""
from . import pages
from flask import render_template, request, jsonify
from app.db.capstones import get_capstones_corpus
from app.routes.decorators import role_required
from app.services.recommender import TopicRecommender


@pages.route("/propose-topic")
@role_required(1)
def propose_topic():
    return render_template("global/propose_topic.html")


@pages.route("/api/topic-similarity", methods=["POST"])
@role_required(1)
def topic_similarity():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('title'), str):
        return jsonify({'error': 'Provide a title as text.'}), 400
    title = data['title'].strip()
    if len(title) > 255:
        return jsonify({'error': 'Title must be 255 characters or fewer.'}), 400

    if len(title) < 4:
        return jsonify({"matches": []})

    corpus = get_capstones_corpus()
    engine = TopicRecommender(corpus)
    matches = engine.find_similar(title, top_n=5)

    return jsonify({"matches": matches})
