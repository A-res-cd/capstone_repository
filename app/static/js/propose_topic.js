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
    const listEl        = document.getElementById('pt-list');

    if (!titleInput) return;

    let debounceTimer = null;
    let inFlight = null;

    function severityFor(score) {
        if (score >= 0.45) return { label: 'High overlap',   cls: 'pt-badge--high'   };
        if (score >= 0.25) return { label: 'Some overlap',   cls: 'pt-badge--medium' };
        return               { label: 'Slight overlap', cls: 'pt-badge--low'    };
    }

    function renderMatches(matches) {
        listEl.innerHTML = '';

        if (!matches.length) {
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

            const li = document.createElement('li');
            li.className = 'pt-match';
            li.innerHTML = `
                <span class="pt-match__icon"><i class="bx bx-file-blank"></i></span>
                <div class="pt-match__body">
                    <span class="pt-match__title">${m.capstone_title}</span>
                    <span class="pt-badge ${sev.cls}">${sev.label} · ${pct}%</span>
                </div>
            `;
            listEl.appendChild(li);
        });
    }

    async function checkSimilarity() {
        const title = titleInput.value.trim();
        const keywords = keywordsInput.value.trim();

        if (title.length < 4) {
            statusEl.textContent = 'Start typing to check for similar existing capstones.';
            emptyEl.hidden = false;
            listEl.hidden = true;
            listEl.innerHTML = '';
            return;
        }

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
            renderMatches(data.matches || []);
        } catch (err) {
            if (err.name !== 'AbortError') {
                statusEl.textContent = 'Could not check similarity right now — try again shortly.';
            }
        }
    }

    function onInput() {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(checkSimilarity, 450);
    }

    titleInput.addEventListener('input', onInput);
    keywordsInput.addEventListener('input', onInput);
});
