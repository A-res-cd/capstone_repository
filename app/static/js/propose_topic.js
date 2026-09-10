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
            setMetric('similarity', title.length >= 4 ? 'Checking archive…' : 'Waiting for a title');
            setMetric('specialization', 'No suggestion yet');
        } else {
            const highestScore = Math.max(0, ...matches.map(match => Number(match.similarity || 0)));
            if (highestScore >= 0.45) setMetric('similarity', `High overlap · ${Math.round(highestScore * 100)}%`, 'danger');
            else if (highestScore >= 0.25) setMetric('similarity', `Some overlap · ${Math.round(highestScore * 100)}%`, 'warning');
            else setMetric('similarity', highestScore ? `Low overlap · ${Math.round(highestScore * 100)}%` : 'No close match found', 'good');

            const specialization = likelySpecialization(matches);
            setMetric('specialization', specialization || 'No confident suggestion', specialization ? 'good' : 'neutral');
        }

        if (title.length < 4) readinessEls.guidance.textContent = 'Enter a working title that describes the problem, users, and technology.';
        else if (hasChecked && matches.some(match => Number(match.similarity) >= 0.45)) readinessEls.guidance.textContent = 'Review the high-overlap capstone and narrow the users, setting, problem, or approach in your proposed title.';
        else if (hasChecked) readinessEls.guidance.textContent = 'Title scores are a starting point. Review the archive and discuss your proposal with your adviser.';
        else readinessEls.guidance.textContent = 'Checking your title against the archive…';
    }

    function severityFor(score) {
        if (score >= 0.45) return { label: 'High overlap',   cls: 'pt-badge--high'   };
        if (score >= 0.25) return { label: 'Some overlap',   cls: 'pt-badge--medium' };
        return               { label: 'Slight overlap', cls: 'pt-badge--low'    };
    }

    function renderMatches(matches) {
        listEl.replaceChildren();
        updateReadiness(matches, true);

        if (!matches.length) {
            emptyTextEl.textContent = 'No similar titles above the 12% display threshold';
            emptyEl.hidden = false;
            listEl.hidden = true;
            statusEl.textContent = 'No similar titles found. Different wording can describe the same topic.';
            return;
        }

        emptyEl.hidden = true;
        listEl.hidden = false;
        statusEl.textContent = `${matches.length} similar title${matches.length > 1 ? 's' : ''} found.`;

        matches.forEach(m => {
            const pct = Math.round(m.similarity * 100);
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
            badge.textContent = `${sev.label} · ${pct}%`;
            body.append(title, badge);

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

        if (title.length < 4) {
            setLoading(false);
            statusEl.textContent = 'Start typing to check for similar existing capstones.';
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
                body: JSON.stringify({ title }),
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
        emptyTextEl.textContent = titleInput.value.trim().length >= 4 ? 'Waiting to check title…' : 'No matches checked yet';
        statusEl.textContent = titleInput.value.trim().length >= 4 ? 'Checking against the archive…' : 'Start typing to check for similar existing capstones.';
        updateReadiness([], false);
        debounceTimer = setTimeout(checkSimilarity, 450);
    }

    titleInput.addEventListener('input', onInput);
    updateReadiness([], false);
});
