from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect

from app.services.recommender import TopicRecommender, keyword_overlap
from app.routes.pages import topics
from tests.test_original_branch_features import feature_app, login


def test_keyword_overlap_uses_whole_unique_phrases():
    overlap = keyword_overlap(' MACHINE  LEARNING, irrigation, irrigation',
                              'machine learning, soil moisture')
    assert overlap['shared'] == ['machine learning']
    assert overlap['shared_count'] == 1 and overlap['union_count'] == 3
    assert overlap['score'] == .333
    assert keyword_overlap('learning', 'machine learning')['score'] == 0
    assert keyword_overlap('machine learning', 'machine learning')['score'] == 1


@pytest.mark.parametrize('proposed,stored', [('', 'machine learning'), ('irrigation', None), (' , ', '')])
def test_missing_keyword_lists_are_not_zero_overlap(proposed, stored):
    assert keyword_overlap(proposed, stored)['score'] is None


def test_keyword_match_is_visible_below_text_cutoff():
    engine = TopicRecommender([dict(capstone_id=1, capstone_title='Warehouse Stock Inventory',
                                   capstone_keywords='image recognition, stock')])
    matches = engine.find_similar('Ocean Coral Reef Monitoring', keywords='image recognition', min_score=.99)
    assert matches[0]['keyword_overlap']['shared'] == ['image recognition']
    assert matches[0]['keyword_overlap']['score'] == .5
    assert matches[0]['similarity'] < .99
    assert engine.find_similar('Ocean Coral Reef Monitoring', keywords='coral', min_score=.99) == []


def test_api_returns_keyword_overlap_and_preserves_text_score(feature_app, monkeypatch):
    client = feature_app.test_client()
    login(client, 1)
    monkeypatch.setattr(topics, 'get_capstones_corpus', lambda: [dict(
        capstone_id=1, capstone_title='Crop Monitoring',
        capstone_keywords='machine learning, farm monitoring, irrigation')])
    response = client.post('/api/topic-similarity', json=dict(
        title='Crop Monitoring', keywords='machine learning, farm monitoring, drought'))
    assert response.status_code == 200
    match = response.json['matches'][0]
    assert 0 <= match['similarity'] <= 1
    assert match['keyword_overlap']['score'] == .5
    assert match['keyword_overlap']['shared_count'] == 2
    assert match['keyword_overlap']['union_count'] == 4


def test_keyword_only_whole_word_matches_rank_before_other_text_matches():
    engine = TopicRecommender([
        dict(capstone_id=1, capstone_title='Learning Tools', capstone_keywords='teaching'),
        dict(capstone_id=2, capstone_title='Warehouse Stock Inventory', capstone_keywords='machine learning'),
    ])
    matches = engine.find_similar('', keywords='learning')
    assert [match['capstone_id'] for match in matches] == [2]
    assert matches[0]['keyword_overlap']['matched_archived'] == ['machine learning']
    assert matches[0]['keyword_overlap']['shared_terms'] == ['learning']
    assert matches[0]['keyword_overlap']['score'] == 0
    assert engine.find_similar('', keywords='earn') == []
    assert engine.find_similar('Learning Tools', keywords='learning')[0]['capstone_id'] == 2


def test_keyword_only_api_returns_archived_keyword_matches(feature_app, monkeypatch):
    client = feature_app.test_client()
    login(client, 1)
    monkeypatch.setattr(topics, 'get_capstones_corpus', lambda: [dict(
        capstone_id=1, capstone_title='Crop Monitoring', capstone_keywords='machine learning')])
    response = client.post('/api/topic-similarity', json={'title': '', 'keywords': 'learning'})
    assert response.status_code == 200
    assert response.json['matches'][0]['keyword_overlap']['shared_terms'] == ['learning']
    assert client.post('/api/topic-similarity', json={'title': '', 'keywords': 'unrelated'}).json['matches'] == []


def test_keyword_only_input_triggers_live_matches(feature_app, page, monkeypatch):
    client = feature_app.test_client()
    login(client, 1)
    monkeypatch.setattr(topics, 'get_capstones_corpus', lambda: [dict(
        capstone_id=1, capstone_title='Crop Monitoring', capstone_keywords='machine learning')])

    def handle(route):
        url = urlsplit(route.request.url)
        if url.netloc != 'topic.test':
            route.abort()
            return
        response = client.open(url.path, method=route.request.method,
                               data=route.request.post_data_buffer,
                               content_type=route.request.headers.get('content-type'))
        route.fulfill(status=response.status_code, body=response.data, content_type=response.content_type)

    page.route('**/*', handle)
    page.goto('http://topic.test/propose-topic')
    page.locator('#pt-keywords').fill('learning')
    expect(page.locator('#pt-title')).to_have_value('')
    expect(page.locator('.pt-match__title')).to_have_text('Crop Monitoring')
    expect(page.locator('.pt-keyword-tag.is-overlap')).to_have_text('✓ machine learning')
    expect(page.locator('.pt-keyword-tag')).to_have_attribute('title', 'Contains a shared keyword term')
    expect(page.locator('#pt-list')).to_contain_text('Shared keyword terms: learning')
    expect(page.locator('.pt-keyword-summary')).to_contain_text('Exact phrases: No overlap · 0.0%')
    page.locator('#pt-keywords').fill('unrelated')
    expect(page.locator('#pt-list')).to_be_hidden()
    page.locator('#pt-keywords').fill('')
    expect(page.locator('#pt-status')).to_have_text('Enter a title or keywords to find related capstones.')


@pytest.mark.parametrize('width', [1280, 390])
def test_keyword_tags_and_band_boundaries(feature_app, page, width):
    client = feature_app.test_client()
    login(client, 1)
    matches = [dict(capstone_id=index, capstone_title=f'Topic {index}: ' + 'Crop Monitoring with Machine Learning for Farm Irrigation and Soil Moisture Assessment ' * 2, similarity=score,
                    matched_keywords=['machine'], keyword_overlap=dict(
                        score=.5, shared=['machine learning', 'farm monitoring'],
                        archived=['machine learning', 'farm monitoring', 'irrigation'],
                        shared_count=2, union_count=4))
               for index, score in enumerate((.299, .30, .699, .70), 1)]

    def handle(route):
        url = urlsplit(route.request.url)
        if url.netloc != 'topic.test':
            route.abort()
            return
        if url.path == '/api/topic-similarity':
            route.fulfill(json={'matches': matches})
            return
        response = client.get(url.path)
        route.fulfill(status=response.status_code, body=response.data, content_type=response.content_type)

    page.route('**/*', handle)
    page.set_viewport_size({'width': width, 'height': 1000})
    page.goto('http://topic.test/propose-topic')
    page.locator('#pt-title').fill('Crop Monitoring')
    page.locator('#pt-keywords').fill('machine learning, farm monitoring, drought')
    expect(page.locator('.pt-match')).to_have_count(4)
    for index, label in enumerate(('Slight overlap', 'Moderate overlap', 'Moderate overlap', 'High overlap')):
        card = page.locator('.pt-match').nth(index)
        expect(card.locator('.pt-badge')).to_contain_text(label)
        expect(card.locator('.pt-keyword-summary')).to_contain_text('Moderate overlap · 50.0% (2 shared / 4 unique phrases)')
        expect(card.locator('.pt-keyword-tag.is-overlap')).to_have_count(2)
        expect(card.locator('.pt-keyword-tag').last).to_have_attribute('title', 'Archived keyword phrase')
    expect(page.locator('#pt-readiness-similarity')).to_contain_text('High overlap · 70.0% score')
    assert page.locator('#page-content').evaluate('el => el.scrollWidth <= el.clientWidth + 1')
    assert page.locator('#pt-list').evaluate('el => el.scrollHeight > el.clientHeight')
    assert page.locator('#pt-list').evaluate('el => el.clientHeight <= Math.min(innerHeight * .55, 480) + 1')
    page.locator('#pt-list').evaluate('el => { el.scrollTop = el.scrollHeight; }')
    assert page.locator('#pt-list').evaluate('el => el.scrollTop > 0')
