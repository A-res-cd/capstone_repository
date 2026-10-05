"""Pages topics routes."""
from . import pages
from flask import render_template, request, jsonify
from app.routes.decorators import role_required
from app.constants.roles import ROLE_STUDENT
from app.services.topics import find_similar_topics


@pages.route("/propose-topic")
@role_required(ROLE_STUDENT)
def propose_topic():
    return render_template("global/propose_title.html")


@pages.route("/api/topic-similarity", methods=["POST"])
@role_required(ROLE_STUDENT)
def topic_similarity():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("title"), str):
        return jsonify({"error": "Provide a title as text."}), 400

    title = data["title"].strip()
    if len(title) > 255:
        return jsonify({"error": "Keep the title within 255 characters."}), 400

    if len(title) < 4:
        return jsonify({"matches": []})

    abstract = data.get("abstract", "")
    keywords = data.get("keywords", "")
    if (not isinstance(abstract, str) or not isinstance(keywords, str)
            or len(abstract) > 10000 or len(keywords) > 1000):
        return jsonify({"error": "Abstract must be text up to 10000 characters; keywords up to 1000."}), 400
    matches = find_similar_topics(title, abstract=abstract, keywords=keywords)

    return jsonify({"matches": matches})
