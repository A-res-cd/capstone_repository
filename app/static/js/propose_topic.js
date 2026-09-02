/* app/static/js/propose_topic.js
 *
 * Debounced live check of a proposed capstone title/keywords against
 * the existing archive, via POST /api/topic-similarity (TF-IDF + cosine
 * similarity computed server-side in app/services/recommender.py).
 */
document.addEventListener('DOMContentLoaded', () => {

    const titleInput    = document.getElementById('pt-title');
    const keywordsInput = document.getElementById('pt-keywords');
    const statusEl      = document.getElementById('pt-status');
    const emptyEl       = document.getElementById('pt-empty');
    const loadingEl     = document.getElementById('pt-loading');
    const listEl        = document.getElementById('pt-list');
    const layoutEl      = document.getElementById('pt-layout');
    const formEl        = document.getElementById('propose-topic-form');
    const resultsEl     = document.getElementById('pt-results');
    const emptyTextEl   = emptyEl?.querySelector('span');
    const readinessEls  = {
        title: document.getElementById('pt-readiness-title'),
        keywords: document.getElementById('pt-readiness-keywords'),
        similarity: document.getElementById('pt-readiness-similarity'),
        specialization: document.getElementById('pt-readiness-specialization'),
        suggestions: document.getElementById('pt-keyword-suggestions'),
        guidance: document.getElementById('pt-readiness-guidance'),
    };
    const metricEls = {
        title: document.getElementById('pt-metric-title'),
        keywords: document.getElementById('pt-metric-keywords'),
        similarity: document.getElementById('pt-metric-similarity'),
        specialization: document.getElementById('pt-metric-specialization'),
    };

    if (!titleInput) return;

    if (formEl && resultsEl && window.ResizeObserver) {
        const syncResultsHeight = () => {
            layoutEl.style.setProperty('--propose-form-height', `${formEl.offsetHeight}px`);
        };
        new ResizeObserver(syncResultsHeight).observe(formEl);
        syncResultsHeight();
    }

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

    function parsedKeywords() {
        return [...new Set(keywordsInput.value
            .split(',')
            .map(keyword => keyword.trim())
            .filter(Boolean))];
    }

    function suggestedKeywords(matches, currentKeywords) {
        const current = new Set(currentKeywords.map(keyword => keyword.toLowerCase()));
        const counts = new Map();

        matches.forEach(match => {
            String(match.capstone_keywords || '').split(',').forEach(rawKeyword => {
                const keyword = rawKeyword.trim();
                const normalized = keyword.toLowerCase();
                if (keyword && !current.has(normalized)) {
                    counts.set(keyword, (counts.get(keyword) || 0) + 1);
                }
            });
        });

        return [...counts.entries()]
            .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
            .slice(0, 6)
            .map(([keyword]) => keyword);
    }

    function likelySpecialization(matches) {
        const scores = new Map();
        matches.forEach(match => {
            const name = String(match.specialization_name || '').trim();
            if (name) scores.set(name, (scores.get(name) || 0) + Number(match.similarity || 0));
        });
        return [...scores.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || '';
    }

    function renderSuggestions(suggestions) {
        readinessEls.suggestions.replaceChildren();
        if (!suggestions.length) {
            const placeholder = document.createElement('span');
            placeholder.className = 'topic-readiness__placeholder';
            placeholder.textContent = 'No related keyword suggestions yet.';
            readinessEls.suggestions.appendChild(placeholder);
            return;
        }

        suggestions.forEach(keyword => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'topic-readiness__keyword';
            button.textContent = `+ ${keyword}`;
            button.addEventListener('click', () => {
                const keywords = parsedKeywords();
                keywords.push(keyword);
                keywordsInput.value = keywords.join(', ');
                onInput();
                keywordsInput.focus();
            });
            readinessEls.suggestions.appendChild(button);
        });
    }

    function updateReadiness(matches = [], hasChecked = false) {
        const title = titleInput.value.trim();
        const titleWords = title.split(/\s+/).filter(Boolean).length;
        const keywords = parsedKeywords();

        if (!title) setMetric('title', 'Add a working title');
        else if (title.length < 20 || titleWords < 4) setMetric('title', 'Add more specific detail', 'warning');
        else if (title.length > 120) setMetric('title', 'Consider a shorter title', 'warning');
        else setMetric('title', `Good length · ${titleWords} words`, 'good');

        if (keywords.length < 3) setMetric('keywords', `Add ${3 - keywords.length} more keyword${keywords.length === 2 ? '' : 's'}`, keywords.length ? 'warning' : 'neutral');
        else if (keywords.length > 8) setMetric('keywords', 'Keep only the most relevant 3–8', 'warning');
        else setMetric('keywords', `${keywords.length} focused keywords`, 'good');

        if (!hasChecked) {
            setMetric('similarity', title.length >= 4 ? 'Checking archive…' : 'Waiting for a title');
            setMetric('specialization', 'No suggestion yet');
            renderSuggestions([]);
        } else {
            const highestScore = Math.max(0, ...matches.map(match => Number(match.similarity || 0)));
            if (highestScore >= 0.45) setMetric('similarity', `High overlap · ${Math.round(highestScore * 100)}%`, 'danger');
            else if (highestScore >= 0.25) setMetric('similarity', `Some overlap · ${Math.round(highestScore * 100)}%`, 'warning');
            else setMetric('similarity', highestScore ? `Low overlap · ${Math.round(highestScore * 100)}%` : 'No close match found', 'good');

            const specialization = likelySpecialization(matches);
            setMetric('specialization', specialization || 'No confident suggestion', specialization ? 'good' : 'neutral');
            renderSuggestions(suggestedKeywords(matches, keywords));
        }

        if (!title) readinessEls.guidance.textContent = 'Enter a specific working title, then add keywords that describe the problem, users, and technology.';
        else if (keywords.length < 3) readinessEls.guidance.textContent = 'Add at least three focused keywords so the archive comparison is more reliable.';
        else if (hasChecked && matches.some(match => Number(match.similarity) >= 0.45)) readinessEls.guidance.textContent = 'Review the high-overlap capstone and narrow the users, setting, problem, or approach in your proposed topic.';
        else if (hasChecked) readinessEls.guidance.textContent = 'Your topic has enough detail. Review the related capstones before discussing it with your adviser.';
        else readinessEls.guidance.textContent = 'Checking your topic against the archive…';
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
            emptyTextEl.textContent = 'No closely related capstones found';
            emptyEl.hidden = false;
            listEl.hidden = true;
            statusEl.textContent = 'No closely related capstones found — this topic looks distinct.';
            return;
        }

        emptyEl.hidden = true;
        listEl.hidden = false;
        statusEl.textContent = `${matches.length} related capstone${matches.length > 1 ? 's' : ''} found.`;

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
        const keywords = keywordsInput.value.trim();

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
                body: JSON.stringify({ title, keywords }),
                signal: controller.signal,
            });
            const data = await res.json();
            if (controller !== inFlight) return;
            setLoading(false);
            renderMatches(data.matches || []);
            inFlight = null;
        } catch (err) {
            if (controller !== inFlight) return;
            setLoading(false);
            if (err.name !== 'AbortError') {
                updateReadiness([], false);
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
        updateReadiness([], false);
        debounceTimer = setTimeout(checkSimilarity, 450);
    }

    titleInput.addEventListener('input', onInput);
    keywordsInput.addEventListener('input', onInput);
    updateReadiness([], false);
});
