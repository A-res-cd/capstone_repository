(function () {
    const page = document.querySelector('.mu-section');
    const dialog = page?.querySelector('#verification-dialog');
    if (!dialog || dialog.dataset.bound) return;
    dialog.dataset.bound = 'true';
    const status = dialog.querySelector('[data-verification-status]');
    const fields = dialog.querySelector('[data-verification-fields]');
    const viewerWrap = dialog.querySelector('[data-verification-viewer-wrap]');
    const viewer = dialog.querySelector('[data-verification-viewer]');
    const rejectionDialog = page.querySelector('#verification-rejection-dialog');
    const rejectionReason = rejectionDialog.querySelector('textarea');
    const rejectButton = dialog.querySelector('[data-verification-reject]');
    const decisionForms = Array.from(page.querySelectorAll('[data-verification-decision-form]'));
    const decisionButtons = [...decisionForms.map(form => form.querySelector('button[type="submit"]')), rejectButton];
    rejectButton.addEventListener('click', () => {
        rejectionReason.setCustomValidity('');
        rejectionDialog.showModal();
        rejectionReason.focus();
    });
    rejectionDialog.querySelector('[data-rejection-cancel]').addEventListener('click', () => rejectionDialog.close());
    rejectionReason.addEventListener('input', () => {
        rejectionReason.setCustomValidity(rejectionReason.value.trim() ? '' : 'Enter a rejection message.');
    });
    rejectionDialog.querySelector('form').addEventListener('submit', event => {
        rejectionReason.value = rejectionReason.value.trim();
        if (!rejectionReason.value) {
            event.preventDefault();
            rejectionReason.setCustomValidity('Enter a rejection message.');
            rejectionReason.reportValidity();
        }
    });
    let controller;

    function setDecisionState(action, enabled) {
        decisionForms.forEach((form) => {
            if (action) form.action = action;
        });
        decisionButtons.forEach((button) => { button.disabled = !enabled; });
    }

    page.addEventListener('click', async (event) => {
        if (event.target.closest('[data-verification-close]')) dialog.close();
        const button = event.target.closest('[data-verification-details]');
        if (!button) return;
        decisionForms.forEach(form => form.reset());
        controller?.abort();
        const active = new AbortController();
        controller = active;
        setDecisionState(button.dataset.verificationAction, false);
        fields.replaceChildren();
        fields.hidden = true;
        viewerWrap.hidden = true;
        viewer.removeAttribute('src');
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
            setDecisionState(button.dataset.verificationAction, true);
            status.textContent = data.document_url ? `COR available (${Math.ceil(data.size_bytes / 1024)} KB). Review the preview below.`
                : data.filename ? 'The COR file is missing or unavailable. Do not approve until the document is available.'
                : 'No COR was uploaded for this account.';
            if (data.document_url) {
                const url = new URL(data.document_url, location.origin);
                if (url.origin !== location.origin) throw new Error('Invalid file link');
                viewer.src = `${url.href}?inline=1`;
                viewerWrap.hidden = false;
            }
        } catch (error) {
            viewerWrap.hidden = true;
            viewer.removeAttribute('src');
            if (error.name !== 'AbortError' && controller === active) status.textContent = 'Could not load verification details. Close this dialog and try again.';
        }
    });
    dialog.addEventListener('close', () => {
        rejectionDialog.close();
        decisionForms.forEach(form => form.reset());
        controller?.abort();
        controller = null;
        setDecisionState('', false);
        viewerWrap.hidden = true;
        viewer.removeAttribute('src');
    });
})();
