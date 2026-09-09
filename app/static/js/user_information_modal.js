(function () {
    if (window.CAPRE_USER_INFO_MODAL_HANDLERS) return;

    let loadPromise;

    function wireModal(modal) {
        modal.querySelectorAll('[data-user-info-close]').forEach((button) => {
            button.addEventListener('click', () => modal.close());
        });
        modal.addEventListener('click', (event) => {
            if (event.target === modal) modal.close();
        });

        const editContactButton = modal.querySelector('#edit-contact-btn');
        const saveContactButton = modal.querySelector('#save-contact-btn');
        const cancelContactButton = modal.querySelector('#cancel-contact-btn');
        const contactForm = modal.querySelector('#contact-info-form');

        if (editContactButton && saveContactButton && cancelContactButton && contactForm) {
            const contactInputs = Array.from(contactForm.querySelectorAll('input:not([type="hidden"])'));
            const initialValues = contactInputs.map((input) => input.value);

            editContactButton.addEventListener('click', () => {
                contactInputs.forEach((input) => input.removeAttribute('readonly'));
                editContactButton.classList.add('hidden');
                saveContactButton.classList.remove('hidden');
                cancelContactButton.classList.remove('hidden');
            });

            cancelContactButton.addEventListener('click', () => {
                contactInputs.forEach((input, index) => {
                    input.value = initialValues[index] || '';
                    input.setAttribute('readonly', 'readonly');
                });
                editContactButton.classList.remove('hidden');
                saveContactButton.classList.add('hidden');
                cancelContactButton.classList.add('hidden');
            });
        }

        const passwordForm = modal.querySelector('#password-form');
        const newPassword = modal.querySelector('#new_password');
        const confirmPassword = modal.querySelector('#confirm_password');
        if (passwordForm && newPassword && confirmPassword) {
            passwordForm.addEventListener('submit', (event) => {
                if (newPassword.value !== confirmPassword.value) {
                    event.preventDefault();
                    confirmPassword.setCustomValidity('Passwords do not match.');
                    confirmPassword.reportValidity();
                }
            });
            confirmPassword.addEventListener('input', () => confirmPassword.setCustomValidity(''));
        }

        const deleteAccountForm = modal.querySelector('#delete-account-form');
        if (deleteAccountForm) {
            deleteAccountForm.addEventListener('submit', (event) => {
                if (!window.confirm('Delete your account permanently?\n\nThis cannot be undone - all your data will be removed and you will be signed out immediately.')) {
                    event.preventDefault();
                }
            });
        }
    }

    async function loadModal(button) {
        if (!loadPromise) {
            const url = button.dataset.userInfoUrl;
            loadPromise = fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
                .then((response) => {
                    if (!response.ok) throw new Error('Could not load user information.');
                    return response.text();
                })
                .then((html) => {
                    const mount = document.createElement('div');
                    mount.innerHTML = html.trim();
                    const modal = mount.querySelector('#user-information-modal');
                    if (!modal) throw new Error('User information modal was not returned.');
                    document.body.appendChild(modal);
                    wireModal(modal);
                    return modal;
                });
        }
        return loadPromise;
    }

    async function openModal(button) {
        try {
            const modal = await loadModal(button);
            if (!modal.open) modal.showModal();
        } catch (error) {
            console.error(error);
        }
    }

    document.addEventListener('click', (event) => {
        const button = event.target.closest('[data-user-info-open]');
        if (button) openModal(button);
    });
    window.CAPRE_USER_INFO_MODAL_HANDLERS = true;

    if (new URLSearchParams(window.location.search).get('user_info') === '1') {
        const opener = document.querySelector('[data-user-info-open]');
        if (opener) openModal(opener);
    }
})();
