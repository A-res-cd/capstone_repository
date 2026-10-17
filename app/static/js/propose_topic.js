/* app/static/js/propose_topic.js
 *
 * Debounced live check of a proposed capstone title against archive
 * titles, via POST /api/topic-similarity (TF-IDF + cosine
 * similarity computed server-side in app/services/recommender.py).
 */
document.addEventListener('DOMContentLoaded', () => {

    const titleInput    = document.getElementById('pt-title');
    const statusEl      = document.getElementById('pt-status');
    const emptyEl       = document.getElementById('pt-empty');
    const loadingEl     = document.getElementById('pt-loading');
    const listEl        = document.getElementById('pt-list');
    const layoutEl      = document.getElementById('pt-layout');
    const formEl        = document.getElementById('propose-topic-form');
    const emptyTextEl   = emptyEl?.querySelector('span');
    const readinessEls  = {
        title: document.getElementById('pt-readiness-title'),
        similarity: document.getElementById('pt-readiness-similarity'),
        specialization: document.getElementById('pt-readiness-specialization'),
        guidance: document.getElementById('pt-readiness-guidance'),
    };
    const metricEls = {
        title: document.getElementById('pt-metric-title'),
        similarity: document.getElementById('pt-metric-similarity'),
        specialization: document.getElementById('pt-metric-specialization'),
    };

    if (!titleInput) return;
    const overlapBands = JSON.parse(formEl.dataset.overlapBands);
    const percentage = score => (Number(score) * 100).toFixed(1);
    const hasSearchInput = () => titleInput.value.trim().length >= 4 || document.getElementById('pt-keywords').value.trim().length > 0;

    formEl.addEventListener('submit', event => event.preventDefault());

    const abstractBaseUrl = layoutEl?.dataset.abstractBaseUrl || '';
    // Base URL ends in ".../0" (capstone_id=0 placeholder) — swap the
    // trailing 0 for the real id per match, same pattern used on the
    // Explore Archive sidebar links.
    function abstractUrlFor(capstoneId) {
        if (!abstractBaseUrl || !capstoneId) return null;
        return abstractBaseUrl.replace(/0$/, String(capstoneId));
    }

    let debounceTimer = null;
    let inFlight = null;

    function setMetric(name, text, state = 'neutral') {
        readinessEls[name].textContent = text;
        metricEls[name].dataset.state = state;
    }

    function likelySpecialization(matches) {
        const scores = new Map();
        matches.forEach(match => {
            const name = String(match.specialization_name || '').trim();
            if (name) scores.set(name, (scores.get(name) || 0) + Number(match.similarity || 0));
        });
        return [...scores.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || '';
    }

    function updateReadiness(matches = [], hasChecked = false) {
        const title = titleInput.value.trim();
        const titleWords = title.split(/\s+/).filter(Boolean).length;

        if (!title) setMetric('title', 'Add a working title');
        else if (title.length < 20 || titleWords < 4) setMetric('title', 'Add more specific detail', 'warning');
        else if (title.length > 120) setMetric('title', 'Consider a shorter title', 'warning');
        else setMetric('title', `Good length · ${titleWords} words`, 'good');

        if (!hasChecked) {
            setMetric('similarity', hasSearchInput() ? 'Checking archive…' : 'Waiting for title or keywords');
            setMetric('specialization', 'No suggestion yet');
        } else {
            const highestScore = Math.max(0, ...matches.map(match => Number(match.similarity || 0)));
            const severity = severityFor(highestScore);
            setMetric('similarity', highestScore ? `${severity.label} · ${percentage(highestScore)}% score` : 'No close match found', severity.tone);

            const specialization = likelySpecialization(matches);
            setMetric('specialization', specialization || 'No confident suggestion', specialization ? 'good' : 'neutral');
        }

        if (title.length < 4) readinessEls.guidance.textContent = hasSearchInput() ? 'Keyword matches can identify related capstones. Add a working title to compare your proposed topic too.' : 'Enter a working title or keywords to find related capstones.';
        else if (hasChecked && matches.some(match => Number(match.similarity) >= overlapBands.high || Number(match.keyword_overlap?.score) >= overlapBands.high)) readinessEls.guidance.textContent = 'Review the high-overlap capstone and narrow the users, setting, problem, or approach in your proposed title.';
        else if (hasChecked) readinessEls.guidance.textContent = 'Title scores are a starting point. Review the archive and discuss your proposal with your adviser.';
        else readinessEls.guidance.textContent = 'Checking your title against the archive…';
    }

    function severityFor(score) {
        if (score >= overlapBands.high) return {label: 'High overlap', cls: 'pt-badge--high', tone: 'danger'};
        if (score >= overlapBands.moderate) return {label: 'Moderate overlap', cls: 'pt-badge--medium', tone: 'warning'};
        return {label: score > 0 ? 'Slight overlap' : 'No overlap', cls: 'pt-badge--low', tone: 'good'};
    }

    function renderMatches(matches) {
        listEl.replaceChildren();
        updateReadiness(matches, true);

        if (!matches.length) {
            emptyTextEl.textContent = 'No text matches above 12% or shared keyword terms found';
            emptyEl.hidden = false;
            listEl.hidden = true;
            statusEl.textContent = 'No related capstones found for this input. Different wording can describe the same topic.';
            return;
        }

        emptyEl.hidden = true;
        listEl.hidden = false;
        statusEl.textContent = `${matches.length} related capstone${matches.length > 1 ? 's' : ''} found.`;

        matches.forEach(m => {
            const pct = percentage(m.similarity);
            const sev = severityFor(m.similarity);
            const href = abstractUrlFor(m.capstone_id);

            const li = document.createElement('li');
            li.className = 'pt-match';

            const row = document.createElement(href ? 'a' : 'div');
            row.className = 'pt-match__link';
            if (href) {
                row.href = href;
                row.target = '_blank';
                row.rel = 'noopener noreferrer';
            }

            const iconWrap = document.createElement('span');
            iconWrap.className = 'pt-match__icon';
            const fileIcon = document.createElement('i');
            fileIcon.className = 'bx bx-file-blank';
            iconWrap.appendChild(fileIcon);

            const body = document.createElement('div');
            body.className = 'pt-match__body';
            const title = document.createElement('span');
            title.className = 'pt-match__title';
            title.textContent = String(m.capstone_title || 'Untitled capstone');
            const badge = document.createElement('span');
            badge.className = `pt-badge ${sev.cls}`;
            badge.textContent = `Text: ${sev.label} · ${pct}% score`;
            body.append(title, badge);
            if (m.matched_keywords?.length) {
                const terms = document.createElement('small');
                terms.textContent = 'Terms found in proposal: ' + m.matched_keywords.join(', ');
                body.appendChild(terms);
            }

            const overlap = m.keyword_overlap;
            if (overlap) {
                const summary = document.createElement('small');
                summary.className = 'pt-keyword-summary';
                if (overlap.score == null) {
                    summary.textContent = overlap.archived.length ? 'Enter keywords to measure keyword overlap.' : 'No archived keywords to compare.';
                } else {
                    const keywordSeverity = severityFor(overlap.score);
                    summary.textContent = `Keywords: ${keywordSeverity.label} · ${percentage(overlap.score)}% (${overlap.shared_count} shared / ${overlap.union_count} unique phrases)`;
                }
                const tags = document.createElement('div');
                tags.className = 'pt-keyword-tags';
                if (overlap.shared_terms?.length) {
                    const terms = document.createElement('small');
                    terms.textContent = 'Shared keyword terms: ' + overlap.shared_terms.join(', ');
                    body.appendChild(terms);
                    if (!overlap.shared.length) summary.textContent = summary.textContent.replace('Keywords:', 'Exact phrases:');
                }
                overlap.archived.forEach(phrase => {
                    const tag = document.createElement('span');
                    const exact = overlap.shared.includes(phrase);
                    const shared = exact || overlap.matched_archived?.includes(phrase);
                    tag.className = 'pt-keyword-tag' + (shared ? ' is-overlap' : '');
                    tag.textContent = (shared ? '✓ ' : '') + phrase;
                    tag.title = exact ? 'Shared keyword phrase' : shared ? 'Contains a shared keyword term' : 'Archived keyword phrase';
                    tags.appendChild(tag);
                });
                body.append(summary, tags);
            }

            row.append(iconWrap, body);
            if (href) {
                const chevron = document.createElement('i');
                chevron.className = 'bx bx-chevron-right pt-match__chevron';
                row.appendChild(chevron);
            }
            li.appendChild(row);
            listEl.appendChild(li);
        });
    }

    function setLoading(isLoading) {
        loadingEl.classList.toggle('hidden', !isLoading);
        if (isLoading) {
            emptyEl.hidden = true;
            listEl.hidden = true;
        }
    }

    async function checkSimilarity() {
        const title = titleInput.value.trim();

        if (!hasSearchInput()) {
            setLoading(false);
            statusEl.textContent = 'Enter a title or keywords to find related capstones.';
            emptyTextEl.textContent = 'No matches checked yet';
            emptyEl.hidden = false;
            listEl.hidden = true;
            listEl.replaceChildren();
            updateReadiness([], false);
            return;
        }

        setLoading(true);
        statusEl.textContent = 'Checking against the archive…';

        if (inFlight) inFlight.abort();
        const controller = new AbortController();
        inFlight = controller;

        try {
            const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
            const res = await fetch('/api/topic-similarity', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(csrfToken ? { 'X-CSRFToken': csrfToken } : {}),
                },
                body: JSON.stringify({ title, abstract: document.getElementById("pt-abstract").value, keywords: document.getElementById("pt-keywords").value }),
                signal: controller.signal,
            });
            const data = await res.json();
            if (controller !== inFlight) return;
            if (!res.ok) throw new Error(data.error || 'Could not check similarity.');
            setLoading(false);
            renderMatches(data.matches || []);
            inFlight = null;
        } catch (err) {
            if (controller !== inFlight) return;
            setLoading(false);
            if (err.name !== 'AbortError') {
                updateReadiness([], false);
                setMetric('similarity', 'Check unavailable');
                readinessEls.guidance.textContent = 'Try checking your title again shortly.';
                emptyTextEl.textContent = 'Similarity check unavailable';
                emptyEl.hidden = false;
                statusEl.textContent = 'Could not check similarity right now — try again shortly.';
            }
            inFlight = null;
        }
    }

    function onInput() {
        clearTimeout(debounceTimer);
        if (inFlight) {
            inFlight.abort();
            inFlight = null;
        }
        setLoading(false);
        listEl.replaceChildren();
        listEl.hidden = true;
        emptyEl.hidden = false;
        emptyTextEl.textContent = hasSearchInput() ? 'Waiting to check title or keywords…' : 'No matches checked yet';
        statusEl.textContent = hasSearchInput() ? 'Checking against the archive…' : 'Enter a title or keywords to find related capstones.';
        updateReadiness([], false);
        debounceTimer = setTimeout(checkSimilarity, 450);
    }

    titleInput.addEventListener('input', onInput);
    document.getElementById('pt-abstract').addEventListener('input', onInput);
    document.getElementById('pt-keywords').addEventListener('input', onInput);
    updateReadiness([], false);
});
