(function () {
    if (window.CAPRE_PASSWORD_FEEDBACK) return;
    window.CAPRE_PASSWORD_FEEDBACK = true;

    function bind(form) {
        if (form.dataset.passwordFeedbackBound) return;
        const password = form.querySelector(`[name="${form.dataset.passwordField || 'new_password'}"]`);
        const confirm = form.querySelector('[name="confirm_password"]');
        if (!password || !confirm) return;
        form.dataset.passwordFeedbackBound = 'true';
        const status = form.querySelector('[data-password-status]');
        const match = form.querySelector('[data-password-match]');

        function update() {
            const value = password.value;
            const rules = {
                length: value.length >= 8 && value.length <= 12,
                uppercase: /[A-Z]/.test(value),
                lowercase: /[a-z]/.test(value),
                number: /[0-9]/.test(value),
            };
            const passed = Object.values(rules).filter(Boolean).length;
            form.querySelectorAll('[data-password-rule]').forEach(item => {
                item.classList.toggle('is-met', rules[item.dataset.passwordRule]);
            });
            password.setCustomValidity(value && passed !== 4 ? 'Use 8–12 characters with uppercase, lowercase and numbers.' : '');
            if (status) {
                status.textContent = !value ? 'Enter a password to check requirements.'
                    : passed === 4 ? 'Password meets all requirements.' : `${passed} of 4 requirements met.`;
                status.classList.toggle('is-met', passed === 4);
            }
            const matches = Boolean(value && confirm.value && value === confirm.value);
            confirm.setCustomValidity(confirm.value && !matches ? 'Passwords do not match.' : '');
            if (match) {
                match.textContent = !confirm.value ? 'Confirm your password.' : matches ? 'Passwords match.' : 'Passwords do not match.';
                match.classList.toggle('is-met', matches);
            }
        }
        password.addEventListener('input', update);
        confirm.addEventListener('input', update);
        form.addEventListener('submit', event => {
            update();
            if (form.id === 'signup-form') return;
            for (const field of [password, confirm]) {
                if (!field.checkValidity()) {
                    event.preventDefault();
                    field.reportValidity();
                    break;
                }
            }
        });
        update();
    }

    function scan(root) {
        if (root.matches?.('[data-password-policy]')) bind(root);
        root.querySelectorAll?.('[data-password-policy]').forEach(bind);
    }
    scan(document);
    new MutationObserver(records => {
        records.forEach(record => record.addedNodes.forEach(node => {
            if (node.nodeType === 1) scan(node);
        }));
    }).observe(document.body, {childList: true, subtree: true});

    document.addEventListener('click', event => {
        const button = event.target.closest('[data-password-toggle]');
        if (!button) return;
        const field = button.closest('form')?.querySelector(`[name="${button.dataset.passwordToggle}"]`);
        if (!field) return;
        const show = field.type === 'password';
        field.type = show ? 'text' : 'password';
        button.setAttribute('aria-pressed', String(show));
        button.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
        const icon = button.querySelector('i');
        if (icon) icon.className = show ? 'bx bx-show' : 'bx bx-hide';
    });
})();
