document.addEventListener('DOMContentLoaded', () => {
    const password = document.querySelector('#password, #new_password');
    const confirm = document.querySelector('#confirm_password');
    const checklist = document.querySelector('[data-password-checklist]');
    const matchStatus = document.querySelector('[data-password-match]');
    if (!password || !checklist) return;

    const rules = {
        length: value => Array.from(value).length >= 8 && Array.from(value).length <= 12,
        uppercase: value => /[A-Z]/.test(value),
        lowercase: value => /[a-z]/.test(value),
        number: value => /[0-9]/.test(value),
    };
    function update() {
        for (const [name, check] of Object.entries(rules)) {
            const item = checklist.querySelector(`[data-rule="${name}"]`);
            const valid = check(password.value);
            item.dataset.valid = String(valid);
            item.setAttribute('aria-label', `${item.textContent}: ${valid ? 'met' : 'not met'}`);
        }
        if (confirm && matchStatus) {
            const matches = confirm.value.length > 0 && password.value === confirm.value;
            matchStatus.textContent = confirm.value ? (matches ? 'Passwords match.' : 'Passwords do not match.') : '';
            matchStatus.dataset.valid = String(matches);
        }
    }
    password.addEventListener('input', update);
    confirm?.addEventListener('input', update);
    update();
});
