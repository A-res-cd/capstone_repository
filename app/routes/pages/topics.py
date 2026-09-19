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

    matches = find_similar_topics(title)

    return jsonify({"matches": matches})
