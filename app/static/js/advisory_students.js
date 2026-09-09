(function () {
    function initStudentPicker(form) {
        if (form.dataset.pickerBound) return;
        form.dataset.pickerBound = 'true';

        const group = form.querySelector('[name="group_id"]');
        const choices = Array.from(form.querySelectorAll('[data-picker-list] input[type="checkbox"]'));
        const search = form.querySelector('[data-picker-search]');
        const confirmation = form.querySelector('[name="confirmed"]');
        const status = form.querySelector('[data-picker-status]');
        const submit = form.querySelector('button[type="submit"]');
        const spaces = form.dataset.groupSpaces ? JSON.parse(form.dataset.groupSpaces) : {};
        const fixedLimit = Number(form.dataset.maxSelection || 0);

        function availablePlaces() {
            return group ? (spaces[group.value] || 0) : fixedLimit;
        }

        function updateSearch() {
            const query = (search?.value || '').trim().toLocaleLowerCase();
            form.querySelectorAll('.advisory-student-choice').forEach((label) => {
                label.hidden = query && !label.textContent.toLocaleLowerCase().includes(query);
            });
        }

        function updateSelection() {
            const available = availablePlaces();
            const selected = choices.filter(choice => choice.checked).length;
            const overLimit = selected > available;
            const needsGroup = group && (!group.value || group.value === '0');
            const needsStudent = !fixedLimit && !selected;

            choices.forEach(choice => {
                choice.disabled = !choice.checked && (!available || selected >= available);
            });
            if (submit) submit.disabled = Boolean(needsGroup || needsStudent || overLimit || (confirmation && selected && !confirmation.checked));
            if (!status) return;

            status.classList.toggle('advisory-error', overLimit);
            if (needsGroup) {
                status.textContent = 'Choose a group, then select students for its available places.';
            } else if (!selected) {
                status.textContent = fixedLimit ? 'Students are optional. You can add them now or later.' : 'Select students for this group.';
            } else if (overLimit) {
                const extra = selected - available;
                status.textContent = `${selected} selected. Only ${available} ${available === 1 ? 'place is' : 'places are'} available. Deselect ${extra} ${extra === 1 ? 'student' : 'students'} to continue.`;
            } else {
                status.textContent = `${selected} of ${available} available ${available === 1 ? 'place' : 'places'} selected.`;
            }
        }

        group?.addEventListener('change', () => {
            choices.forEach(choice => {
                choice.checked = false;
            });
            updateSelection();
        });
        search?.addEventListener('input', updateSearch);
        form.addEventListener('change', updateSelection);
        updateSearch();
        updateSelection();
    }

    document.querySelectorAll('[data-student-picker]').forEach(initStudentPicker);

    if (!window.CAPRE_ADVISORY_MODAL_HANDLERS) {
        document.addEventListener('click', (event) => {
            const openButton = event.target.closest('[data-modal-open]');
            if (openButton) {
                const modal = document.getElementById(openButton.dataset.modalOpen);
                if (modal && !modal.open) modal.showModal();
                return;
            }

            const closeButton = event.target.closest('[data-modal-close]');
            if (closeButton) closeButton.closest('dialog')?.close();
        });
        window.CAPRE_ADVISORY_MODAL_HANDLERS = true;
    }

    document.querySelectorAll('.advisory-modal').forEach((modal) => {
        if (modal.dataset.backdropBound) return;
        modal.dataset.backdropBound = 'true';
        modal.addEventListener('click', (event) => {
            if (event.target === modal) modal.close();
        });
    });
})();
