document.addEventListener('DOMContentLoaded', () => {
    const form = document.querySelector('.archive-filters .filter-form');
    const results = document.querySelector('.archive-layout-wrapper');
    const status = document.getElementById('archive-filter-status');
    if (!form || !results || !status) return;
    let controller;

    async function refresh(url) {
        controller?.abort();
        const pending = new AbortController();
        controller = pending;
        results.setAttribute('aria-busy', 'true');
        status.hidden = false;
        status.textContent = 'Loading capstones…';
        try {
            const response = await fetch(url, {
                headers: {'X-Requested-With': 'XMLHttpRequest'},
                signal: pending.signal,
            });
            if (response.redirected) {
                window.location.assign(response.url);
                return;
            }
            if (!response.ok) throw new Error('Archive filter failed');
            const documentNext = new DOMParser().parseFromString(await response.text(), 'text/html');
            const nextResults = documentNext.querySelector('.archive-layout-wrapper');
            const nextForm = documentNext.querySelector('.archive-filters .filter-form');
            if (!nextResults || !nextForm) throw new Error('Missing archive results');
            if (pending.signal.aborted) return;
            results.replaceChildren(...nextResults.childNodes);
            document.body.classList.remove('archive-mobile-detail-open');
            nextForm.querySelectorAll('input, select').forEach(field => {
                const current = form.elements.namedItem(field.name);
                if (!current) return;
                current.value = field.value;
                if (current.tagName === 'SELECT') window.CAPRE?.syncSelect(current);
                if (field.hasAttribute('placeholder')) current.placeholder = field.placeholder;
            });
            form.querySelector('.btn-clear')?.remove();
            const clear = nextForm.querySelector('.btn-clear');
            if (clear) form.append(clear);
            history.replaceState(null, '', url);
            document.dispatchEvent(new Event('archive:updated'));
            status.textContent = results.querySelector('.archive-results-count')?.textContent.trim()
                || 'No capstones found.';
        } catch (error) {
            if (error.name !== 'AbortError') {
                status.textContent = 'Could not load capstones. Please try Apply again.';
            }
        } finally {
            if (controller === pending) results.removeAttribute('aria-busy');
        }
    }

    form.addEventListener('submit', event => {
        event.preventDefault();
        const url = new URL(form.action, location.origin);
        new FormData(form).forEach((value, key) => url.searchParams.set(key, value));
        refresh(url);
    });

    document.querySelector('.explore-archive-container').addEventListener('click', event => {
        const link = event.target.closest('.archive-pagination-bar a, .filter-form .btn-clear');
        if (!link || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        refresh(new URL(link.href));
    });
});
