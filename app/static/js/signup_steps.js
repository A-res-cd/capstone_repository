document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('signup-form');
    if (!form) return;
    const steps = Array.from(form.querySelectorAll('[data-signup-step]'));
    const labels = form.querySelectorAll('[data-step-label]');
    const back = form.querySelector('[data-signup-back]');
    const next = form.querySelector('[data-signup-next]');
    const submit = document.getElementById('signup-submit');
    const error = document.getElementById('signup-step-error');
    const preference = form.querySelector('[name="preferred_contact"]');
    const contactFields = form.querySelectorAll('[data-contact-field]');
    let current = Math.max(0, steps.findIndex(step => step.querySelector('.field-error')));
    let furthest = current;
    let submitting = false;
    const submitLabel = submit.innerHTML;

    function updateContact() {
        contactFields.forEach(group => {
            const selected = group.dataset.contactField === preference.value;
            group.hidden = !selected;
            const input = group.querySelector('input');
            input.disabled = !selected;
            input.required = selected;
        });
    }

    function updateReview() {
        const values = [
            ['COR', document.getElementById('cor').files[0]?.name || 'Upload required'],
            ['Name', ['first_name', 'middle_name', 'last_name'].map(name => form.elements[name].value).filter(Boolean).join(' ')],
            ['Student number', form.elements.student_no.value || 'Not provided'],
            ['Username', form.elements.username.value],
            ['Preferred contact', preference.value === 'phone' ? 'Phone' : 'Email'],
            ['Contact details', form.elements[preference.value]?.value || ''],
        ];
        const review = document.getElementById('signup-review');
        review.replaceChildren();
        values.forEach(([label, value]) => {
            const term = document.createElement('dt');
            const detail = document.createElement('dd');
            term.textContent = label;
            detail.textContent = value;
            review.append(term, detail);
        });
    }

    function show(index) {
        current = index;
        furthest = Math.max(furthest, current);
        steps.forEach((step, i) => { step.hidden = i !== current; });
        labels.forEach((label, i) => {
            label.classList.toggle('is-active', i === current);
            label.disabled = i > furthest;
            if (i === current) label.setAttribute('aria-current', 'step');
            else label.removeAttribute('aria-current');
        });
        back.hidden = current === 0;
        next.hidden = current === steps.length - 1;
        submit.hidden = current !== steps.length - 1;
        error.hidden = true;
        updateReview();
        Array.from(steps[current].querySelectorAll('input, select')).find(input => !input.disabled && !input.closest('[hidden]'))?.focus();
    }

    function validateStep(index) {
        if (index === 2 && !['email', 'phone'].includes(preference.value)) {
            error.textContent = 'Choose email or phone to continue.';
            error.hidden = false;
            return false;
        }
        if (index === 0 && !document.getElementById('cor').files.length) {
            error.textContent = 'Upload your COR PDF to continue.';
            error.hidden = false;
            return false;
        }
        for (const input of steps[index].querySelectorAll('input, select')) {
            if (!input.checkValidity()) {
                input.reportValidity();
                return false;
            }
        }
        if (index === 1) {
            const password = document.getElementById('password').value;
            const confirmed = form.querySelector('[name="confirm_password"]').value;
            let message = '';
            if (!/^(?=.{8,12}$)(?=.*[A-Z])(?=.*[a-z])(?=.*[0-9]).*$/.test(password)) {
                message = 'Use 8–12 characters with uppercase, lowercase and numbers.';
            } else if (password !== confirmed) {
                message = 'Passwords do not match.';
            }
            if (message) {
                error.textContent = message;
                error.hidden = false;
                return false;
            }
        }
        return true;
    }

    form.querySelector('.signup-actions').hidden = false;
    document.getElementById('cor-extraction').hidden = false;
    preference.addEventListener('change', updateContact);
    updateContact();
    labels.forEach((label, index) => {
        label.addEventListener('click', () => { if (index <= furthest) show(index); });
    });
    back.addEventListener('click', () => show(current - 1));
    next.addEventListener('click', () => { if (validateStep(current)) show(current + 1); });
    form.addEventListener('submit', event => {
        event.preventDefault();
        if (submitting) return;
        if (current !== steps.length - 1) {
            if (validateStep(current)) show(current + 1);
            return;
        }
        for (let i = 0; i < steps.length; i++) {
            show(i);
            if (!validateStep(i)) return;
        }
        submitting = true;
        submit.disabled = true;
        submit.textContent = 'Creating account...';
        form.setAttribute('aria-busy', 'true');
        back.disabled = true;
        next.disabled = true;
        labels.forEach(label => { label.disabled = true; });
        form.submit();
    });
    window.addEventListener('pageshow', event => {
        if (!event.persisted) return;
        submitting = false;
        submit.disabled = false;
        submit.innerHTML = submitLabel;
        form.removeAttribute('aria-busy');
        back.disabled = false;
        next.disabled = false;
        show(current);
    });
    show(current);
});
