"""Match proposed titles, abstracts and keywords against the repository corpus."""
from app.db.capstones import get_capstones_corpus
from app.services.recommender import TopicRecommender


def find_similar_topics(title, abstract="", keywords=""):
    corpus = get_capstones_corpus()
    return TopicRecommender(corpus).find_similar(title, top_n=5, abstract=abstract, keywords=keywords)
