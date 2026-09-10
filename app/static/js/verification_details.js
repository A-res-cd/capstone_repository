(function () {
    const page = document.querySelector('.mu-section');
    const dialog = page?.querySelector('#verification-dialog');
    if (!dialog || dialog.dataset.bound) return;
    dialog.dataset.bound = 'true';
    const status = dialog.querySelector('[data-verification-status]');
    const fields = dialog.querySelector('[data-verification-fields]');
    const file = dialog.querySelector('[data-verification-file]');
    let controller;

    page.addEventListener('click', async (event) => {
        if (event.target.closest('[data-verification-close]')) dialog.close();
        const button = event.target.closest('[data-verification-details]');
        if (!button) return;
        controller?.abort();
        const active = new AbortController();
        controller = active;
        fields.replaceChildren();
        fields.hidden = true;
        file.hidden = true;
        file.removeAttribute('href');
        status.textContent = 'Loading account details…';
        dialog.showModal();
        try {
            const response = await fetch(button.dataset.verificationDetails, {signal: active.signal, cache: 'no-store'});
            if (!response.ok || response.redirected) throw new Error('Unavailable');
            const data = await response.json();
            if (controller !== active || !dialog.isConnected) return;
            const labels = {
                request_id: 'Verification request', user_id: 'Account ID', full_name: 'Full name',
                username: 'Username', email: 'Primary email', university_no: 'University number', role_name: 'Role',
                account_status: 'Account status', request_status: 'Verification status',
                request_date: 'Requested at (UTC)', filename: 'COR filename',
            };
            for (const [key, label] of Object.entries(labels)) {
                const term = document.createElement('dt');
                const value = document.createElement('dd');
                term.textContent = label;
                value.textContent = data[key] || 'Not provided';
                fields.append(term, value);
            }
            fields.hidden = false;
            status.textContent = data.document_url ? `COR available (${Math.ceil(data.size_bytes / 1024)} KB).`
                : data.filename ? 'The COR file is missing or unavailable. Do not approve until the document is available.'
                : 'No COR was uploaded for this account.';
            if (data.document_url) {
                const url = new URL(data.document_url, location.origin);
                if (url.origin !== location.origin) throw new Error('Invalid file link');
                file.href = url.href;
                file.setAttribute('download', data.filename || 'cor.pdf');
                file.hidden = false;
            }
        } catch (error) {
            if (error.name !== 'AbortError' && controller === active) status.textContent = 'Could not load verification details. Close this dialog and try again.';
        }
    });
    dialog.addEventListener('close', () => { controller?.abort(); controller = null; });
})();
