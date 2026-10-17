document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('request-filter-form');
    const list = document.getElementById('request-list');
    if (!form || !list) return;

    form.addEventListener('submit', async event => {
        event.preventDefault();
        const url = new URL(form.action, location.origin);
        new FormData(form).forEach((value, key) => url.searchParams.set(key, value));
        form.setAttribute('aria-busy', 'true');
        try {
            const response = await fetch(url, {headers: {'X-Requested-With': 'XMLHttpRequest'}});
            if (!response.ok) throw new Error('Request filter failed');
            list.innerHTML = await response.text();
            history.replaceState(null, '', url);
            document.getElementById('sidebar-empty').style.display = 'flex';
            document.getElementById('sidebar-detail').style.display = 'none';
        } catch {
            form.submit();
        } finally {
            form.removeAttribute('aria-busy');
        }
    });
});
