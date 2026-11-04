document.addEventListener('DOMContentLoaded', () => {
    const box = document.querySelector('[data-verification-url]');
    if (!box) return;
    const form = document.getElementById('signup-form');
    const email = document.getElementById('email');
    const code = document.getElementById('signup-email-code');
    const entry = document.getElementById('signup-code-entry');
    const send = document.getElementById('signup-send-code');
    const verify = document.getElementById('signup-verify-code');
    const change = document.getElementById('signup-change-email');
    const status = document.getElementById('signup-email-status');
    let pending = false;

    function verified(value) {
        form.dataset.emailVerified = String(value);
        email.readOnly = value;
        send.hidden = value;
        change.hidden = !value;
        if (!form.querySelector('[data-signup-step]').hidden) {
            form.querySelector('[data-signup-next]').hidden = !value;
        }
        if (value) {
            entry.hidden = true;
            code.value = '';
        }
    }
    verified(false);

    async function request(action) {
        if (pending || !email.reportValidity()) return;
        if (action === 'verify' && !/^[0-9]{6}$/.test(code.value)) {
            status.textContent = 'Enter the six-digit code from your email.';
            code.focus();
            return;
        }
        pending = true;
        send.disabled = verify.disabled = true;
        email.readOnly = true;
        status.textContent = action === 'send' ? 'Sending your code…' : 'Checking your code…';
        const data = new FormData();
        data.set('email', email.value);
        data.set('code', code.value);
        data.set('action', action);
        data.set('csrf_token', form.elements.csrf_token?.value || '');
        try {
            const response = await fetch(box.dataset.verificationUrl, {
                method: 'POST', body: data, headers: {'X-Requested-With': 'XMLHttpRequest'},
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Please try again.');
            if (result.verified) {
                email.value = result.email;
                verified(true);
                status.textContent = 'Email verified. Continue with your document.';
                document.dispatchEvent(new Event('signup:email-verified'));
                const upload = document.getElementById('cor');
                if (upload.files.length) upload.dispatchEvent(new Event('change'));
            } else {
                entry.hidden = false;
                send.textContent = 'Send a new code';
                status.textContent = result.message;
                code.value = '';
                code.focus();
            }
        } catch (error) {
            status.textContent = error instanceof SyntaxError ? 'Could not verify email. Please try again.' : error.message;
        } finally {
            pending = false;
            send.disabled = verify.disabled = false;
            email.readOnly = form.dataset.emailVerified === 'true';
        }
    }
    send.addEventListener('click', () => request('send'));
    verify.addEventListener('click', () => request('verify'));
    code.addEventListener('keydown', event => {
        if (event.key === 'Enter') { event.preventDefault(); request('verify'); }
    });
    change.addEventListener('click', () => {
        verified(false);
        entry.hidden = true;
        status.textContent = '';
        const upload = document.getElementById('cor');
        upload.value = '';
        upload.dispatchEvent(new Event('change'));
        email.focus();
    });
    document.addEventListener('signup:email-required', () => {
        verified(false);
        status.textContent = 'Email verification expired. Request a new code to continue.';
    });
    const originalEmail = email.value;
    fetch(box.dataset.verificationUrl, {headers: {'X-Requested-With': 'XMLHttpRequest'}})
        .then(response => response.ok ? response.json() : null)
        .then(result => {
            if (!result?.verified || pending || email.value !== originalEmail) return;
            email.value = result.email;
            verified(true);
            status.textContent = 'Your email is already verified.';
        }).catch(() => {});
});
