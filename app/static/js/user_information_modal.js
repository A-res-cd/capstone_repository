(function () {
    if (window.CAPRE_USER_INFO_MODAL_HANDLERS) return;

    let loadPromise;

    function getAvatarViewer() {
        let viewer = document.getElementById('avatar-viewer');
        if (viewer) return viewer;

        viewer = document.createElement('dialog');
        viewer.id = 'avatar-viewer';
        viewer.className = 'avatar-viewer';
        viewer.setAttribute('aria-label', 'Profile image viewer');
        viewer.innerHTML = `
            <div class="avatar-viewer__content">
                <button type="button" class="avatar-viewer__close" aria-label="Close image viewer">&times;</button>
                <img class="avatar-viewer__image" alt="">
            </div>
        `;
        document.body.appendChild(viewer);

        viewer.querySelector('.avatar-viewer__close').addEventListener('click', () => viewer.close());
        viewer.addEventListener('click', (event) => {
            if (event.target === viewer) viewer.close();
        });
        return viewer;
    }

    function openAvatarViewer(trigger) {
        const viewer = getAvatarViewer();
        const image = viewer.querySelector('.avatar-viewer__image');
        image.src = trigger.dataset.avatarView;
        image.alt = trigger.dataset.avatarAlt || 'Profile image';
        if (!viewer.open) viewer.showModal();
    }

    function wireAvatarViewer(container) {
        const triggers = Array.from(container.querySelectorAll('[data-avatar-view]'));
        triggers.forEach((trigger) => {
            if (trigger.dataset.avatarViewerBound) return;
            trigger.dataset.avatarViewerBound = 'true';

            const activate = (event) => {
                if (event.type === 'keydown' && !['Enter', ' '].includes(event.key)) return;
                event.preventDefault();
                event.stopPropagation();
                openAvatarViewer(trigger);
            };
            trigger.addEventListener('click', activate);
            trigger.addEventListener('keydown', activate);
        });
    }

    function wireAvatarPreview(container) {
        const form = container.querySelector('.avatar-upload-form');
        const input = form?.querySelector('input[type="file"]');
        const wrap = form?.querySelector('[data-avatar-preview-wrap]');
        const preview = form?.querySelector('[data-avatar-preview]');
        const name = form?.querySelector('[data-avatar-preview-name]');
        if (!form || !input || !wrap || !preview || input.dataset.previewBound) return;

        input.dataset.previewBound = 'true';
        input.addEventListener('change', () => {
            const file = input.files?.[0];
            if (!file) {
                wrap.hidden = true;
                preview.removeAttribute('src');
                return;
            }

            const objectUrl = URL.createObjectURL(file);
            preview.src = objectUrl;
            preview.onload = () => URL.revokeObjectURL(objectUrl);
            if (name) name.textContent = file.name;
            wrap.hidden = false;
        });
    }

    function wireModal(modal) {
        wireAvatarPreview(modal);
        wireAvatarViewer(modal);
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
    document.querySelectorAll('.avatar-upload-form').forEach(wireAvatarPreview);
    wireAvatarViewer(document);
    window.CAPRE_USER_INFO_MODAL_HANDLERS = true;

    if (new URLSearchParams(window.location.search).get('user_info') === '1') {
        const opener = document.querySelector('[data-user-info-open]');
        if (opener) openModal(opener);
    }
})();
