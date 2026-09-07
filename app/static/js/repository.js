document.addEventListener('DOMContentLoaded', () => {
    const deleteModal = document.getElementById('delete-confirm-modal');
    const deleteMessage = document.getElementById('delete-confirm-message');
    const deleteNote = document.getElementById('delete-confirm-note');
    const deleteClose = document.getElementById('delete-confirm-close');
    const deleteCancel = document.getElementById('delete-confirm-cancel');
    const deleteSubmit = document.getElementById('delete-confirm-submit');
    const deleteSpinner = document.getElementById('delete-confirm-spinner');
    const deleteLabel = document.getElementById('delete-confirm-label');
    let deleteEndpoint = '';
    let deleteTimer = null;
    let deleteTrigger = null;

    function submitDelete() {
        if (!deleteEndpoint || deleteSubmit.disabled) return;
        deleteSubmit.disabled = true;
        deleteSpinner.hidden = false;
        deleteLabel.textContent = 'Deleting...';

        const token = document.querySelector('meta[name="csrf-token"]')?.content;
        const f = document.createElement('form');
        f.method = 'POST';
        f.action = deleteEndpoint;
        if (token) {
            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = 'csrf_token';
            input.value = token;
            f.appendChild(input);
        }
        document.body.appendChild(f);
        f.submit();
    }

    function closeDeleteModal() {
        if (!deleteModal || deleteModal.hidden) return;
        window.clearInterval(deleteTimer);
        deleteTimer = null;
        deleteModal.hidden = true;
        document.body.classList.remove('repo-modal-open');
        deleteTrigger?.focus();
        deleteTrigger = null;
        deleteEndpoint = '';
    }

    function openDeleteModal(trigger) {
        if (!deleteModal) return;
        const itemName = trigger.dataset.deleteItem || 'Untitled item';
        const isPermanent = trigger.dataset.deleteMode === 'permanent';
        let secondsLeft = 5;

        deleteTrigger = trigger;
        deleteEndpoint = trigger.dataset.deleteEndpoint || '';
        deleteMessage.textContent = `Are you sure you want to delete this item: ${itemName}?`;
        deleteNote.textContent = isPermanent
            ? 'This action permanently deletes the item and cannot be undone.'
            : 'This item will be moved to the Recycle Bin and can be restored later.';
        deleteSubmit.disabled = true;
        deleteSpinner.hidden = false;
        deleteLabel.textContent = `Confirm (${secondsLeft})`;
        deleteModal.hidden = false;
        document.body.classList.add('repo-modal-open');
        deleteCancel.focus();

        window.clearInterval(deleteTimer);
        deleteTimer = window.setInterval(() => {
            secondsLeft -= 1;
            if (secondsLeft > 0) {
                deleteLabel.textContent = `Confirm (${secondsLeft})`;
                return;
            }
            window.clearInterval(deleteTimer);
            deleteTimer = null;
            deleteSpinner.hidden = true;
            deleteSubmit.disabled = false;
            deleteLabel.textContent = 'Confirm';
        }, 1000);
    }

    document.querySelectorAll('[data-delete-trigger]').forEach((trigger) => {
        trigger.addEventListener('click', () => openDeleteModal(trigger));
    });
    deleteClose?.addEventListener('click', closeDeleteModal);
    deleteCancel?.addEventListener('click', closeDeleteModal);
    deleteSubmit?.addEventListener('click', submitDelete);
    deleteModal?.addEventListener('click', (event) => {
        if (event.target === deleteModal) closeDeleteModal();
    });
    deleteModal?.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') closeDeleteModal();
    });

    // ── Panel switching ─────────────────────────────────────
    const panelForm = document.getElementById('panel-form');
    const btnOpenCreate = document.getElementById('btn-open-create');
    const btnCloseForm = document.getElementById('btn-close-form');
    const btnCancel = document.getElementById('btn-cancel');
    let preserveCreateDraft = false;
    let peopleLoadVersion = 0;
    let peopleReady = true;
    let editTrigger = null;

    // Recycle Bin has no repository form panel.
    if (!panelForm || !btnOpenCreate || !btnCloseForm || !btnCancel) return;

    function openCreate() {
        if (!preserveCreateDraft) {
            resetForm();
            document.getElementById('form-heading').textContent = 'New Capstone';
            document.getElementById('form-subheading').textContent = 'Fill in the details to add a capstone to the archive.';
            document.getElementById('btn-submit-label').textContent = 'Submit Capstone';
            setText('file-label-note', '(required)');
            setText('current-file-note', '');
            setDisplay('extract-section', 'block');
            document.getElementById('extract-file-input').required = true;
            document.getElementById('capstone-form').action =
                "/repository/create";
        }
        preserveCreateDraft = false;
        showForm();
    }
    // exposed on window: repository.html calls this from an inline onclick="" attribute
    window.openCreate = openCreate;

    function openEdit(btn) {
        preserveCreateDraft = false;
        resetForm();
        editTrigger = btn;
        const loadVersion = peopleLoadVersion;
        peopleReady = false;
        document.getElementById('btn-submit').disabled = true;
        document.querySelectorAll('.people-section').forEach(section => { section.disabled = true; });
        setText('people-load-status', 'Loading author account links...');
        document.getElementById('people-load-status').hidden = false;

        const id = btn.dataset.id;
        const title = btn.dataset.title;
        const keywords = btn.dataset.keywords;
        const program = btn.dataset.program;
        const spec = btn.dataset.spec;
        const year = btn.dataset.year;
        const semester = btn.dataset.semester;
        const file = btn.dataset.file;
        const utilized = btn.dataset.utilized === 'true';
        const presented = btn.dataset.presented === 'true';
        const copyrightRegistered = btn.dataset.copyright === 'true';

        document.getElementById('field-capstone-id').value = id;
        document.getElementById('capstone_title').value = title;
        document.getElementById('capstone_keywords').value = keywords;
        document.getElementById('capstone_year').value = year;
        document.getElementById('is_utilized').checked = utilized;
        document.getElementById('is_presented').checked = presented;
        document.getElementById('is_copyright_registered').checked = copyrightRegistered;

        // select dropdowns
        setSelect('program_id', program);
        setSelect('specialization_id', spec);
        setSelect('semester', semester);

        document.getElementById('form-heading').textContent = 'Edit Capstone';
        document.getElementById('form-subheading').textContent = 'Update the details for this capstone record.';
        document.getElementById('btn-submit-label').textContent = 'Save Changes';
        setText('file-label-note', '(leave blank to keep existing)');
        setText('current-file-note', file ? ' · Current: ' + file : ' · No file uploaded');
        setDisplay('extract-section', 'none');
        document.getElementById('extract-file-input').required = false;

        document.getElementById('capstone-form').action =
            "/repository/update/" + id;

        // Authors/adviser aren't in the record-card's data-* attributes
        // (would bloat every row's HTML) — fetched separately and filled
        // in once they arrive, without blocking the panel from opening.
        fetch(`/repository/${id}/people`)
            .then(r => {
                if (!r.ok) throw new Error('People request failed');
                return r.json();
            })
            .then(data => {
                if (loadVersion !== peopleLoadVersion) return;
                if (!data.success) throw new Error('People request failed');
                data.authors.forEach((author, i) => {
                    setField(`authors-${i}-author_id`, author.author_id || '');
                    setField(`authors-${i}-user_id`, author.user_id || 0);
                    setField(`authors-${i}-first_name`, author.first || '');
                    setField(`authors-${i}-middle_name`, author.middle || '');
                    setField(`authors-${i}-last_name`, author.last || '');
                });
                if (data.adviser) {
                    setField('adviser-author_id', data.adviser.author_id || '');
                    setField('adviser-first_name', data.adviser.first || '');
                    setField('adviser-middle_name', data.adviser.middle || '');
                    setField('adviser-last_name', data.adviser.last || '');
                }
                peopleReady = true;
                document.getElementById('btn-submit').disabled = false;
                document.querySelectorAll('.people-section').forEach(section => { section.disabled = false; });
                document.getElementById('people-load-status').hidden = true;
            })
            .catch(() => {
                if (loadVersion !== peopleLoadVersion) return;
                setText('people-load-status', 'Could not load author links. Close and reopen this capstone before saving.');
            });

        showForm();
    }

    function setSelect(id, value) {
        const sel = document.getElementById(id);
        for (let opt of sel.options) {
            if (opt.value == value) { opt.selected = true; break; }
        }
    }

    function resetForm() {
        peopleLoadVersion += 1;
        peopleReady = true;
        editTrigger = null;
        document.getElementById('capstone-form').reset();
        document.getElementById('btn-submit').disabled = false;
        document.querySelectorAll('.people-section').forEach(section => { section.disabled = false; });
        document.getElementById('people-load-status').hidden = true;
        for (let i = 0; i < 4; i += 1) {
            setField(`authors-${i}-author_id`, '');
            setField(`authors-${i}-user_id`, 0);
        }
        setField('adviser-author_id', '');
        document.getElementById('field-capstone-id').value = '';
        setField('extracted-filename', '');
        setDisplay('keyword-chips', 'none');
        setDisplay('extract-status', 'none');
        goToStep(1);
    }

    // ── Two-step wizard: Capstone Details → Authors ─────────
    const formSteps = document.querySelectorAll('.form-step');
    const stepDots = document.querySelectorAll('[data-step-dot]');

    function goToStep(stepNum) {
        formSteps.forEach(step => {
            step.classList.toggle('form-step--hidden', step.dataset.step != stepNum);
        });
        stepDots.forEach(dot => {
            const n = Number(dot.dataset.stepDot);
            dot.classList.toggle('form-step-dot--active', n === stepNum);
            dot.classList.toggle('form-step-dot--done', n < stepNum);
        });
        panelForm.scrollTop = 0;
    }

    // Validates only the fields inside step 1 before advancing — step 2's
    // required adviser fields stay untouched/hidden at this point, so they
    // can't block this check.
    function validateStep1() {
        const step1 = document.querySelector('.form-step[data-step="1"]');
        const fields = step1.querySelectorAll('input[required], select[required]');
        for (const field of fields) {
            if (!field.reportValidity()) return false;
        }
        return true;
    }

    document.getElementById('btn-step-next').addEventListener('click', () => {
        if (validateStep1()) goToStep(2);
    });
    document.getElementById('btn-step-back').addEventListener('click', () => goToStep(1));
    document.getElementById('capstone-form').addEventListener('submit', event => {
        if (!peopleReady) {
            event.preventDefault();
            goToStep(2);
        }
    });
    document.getElementById('btn-reset').addEventListener('click', event => {
        event.preventDefault();
        if (editTrigger) openEdit(editTrigger);
        else resetForm();
    });

    function setText(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    }

    function setDisplay(id, value) {
        const el = document.getElementById(id);
        if (el) el.style.display = value;
    }

    function showForm() {
        panelForm.classList.remove('repo-panel--hidden');
        document.body.classList.add('repo-modal-open');
    }

    function showList() {
        panelForm.classList.add('repo-panel--hidden');
        document.body.classList.remove('repo-modal-open');
    }

    function closeForm() {
        preserveCreateDraft = false;
        showList();
    }

    btnOpenCreate.addEventListener('click', openCreate);
    btnCloseForm.addEventListener('click', closeForm);
    btnCancel.addEventListener('click', closeForm);
    document.getElementById('btn-cancel-2')?.addEventListener('click', closeForm);
    panelForm.addEventListener('click', event => {
        if (event.target !== panelForm) return;
        preserveCreateDraft = !document.getElementById('field-capstone-id').value;
        showList();
    });

    // Wire up all Edit buttons
    document.querySelectorAll('.btn-row--edit').forEach(btn => {
        btn.addEventListener('click', () => openEdit(btn));
    });

    const extractInput = document.getElementById('extract-file-input');
    const extractStatus = document.getElementById('extract-status');
    const extractedFilenameInput = document.getElementById('extracted-filename');

    // Builds the status line as real DOM nodes instead of a template
    // template string; the icon class is always ours, but the
    // message text may contain a filename or server text we don't fully
    // control, so it's inserted as a text node, never as raw HTML.
    function setExtractStatus(iconClass, message, dismissible = false) {
        extractStatus.replaceChildren();
        const icon = document.createElement('i');
        icon.className = iconClass;
        extractStatus.appendChild(icon);

        const messageText = document.createElement('span');
        messageText.className = 'extract-status__message';
        messageText.textContent = message;
        extractStatus.appendChild(messageText);

        if (dismissible) {
            const closeButton = document.createElement('button');
            closeButton.type = 'button';
            closeButton.className = 'extract-status__close';
            closeButton.setAttribute('aria-label', 'Dismiss notification');
            closeButton.title = 'Dismiss';

            const closeIcon = document.createElement('i');
            closeIcon.className = 'bx bx-x';
            closeButton.appendChild(closeIcon);
            closeButton.addEventListener('click', () => {
                extractStatus.style.display = 'none';
            });
            extractStatus.appendChild(closeButton);
        }
    }

    if (extractInput) {
        extractInput.addEventListener('change', async () => {
            const file = extractInput.files[0];
            if (!file) return;

            extractStatus.style.display = 'block';
            extractStatus.className = 'extract-status extract-status--loading';
            setExtractStatus('bx bx-loader-alt bx-spin', 'Reading PDF...');

            const formData = new FormData();
            formData.append('capstone_file', file);
            formData.append('csrf_token', document.querySelector('input[name="csrf_token"]').value);

            try {
                const resp = await fetch(extractInput.dataset.extractUrl, {
                    method: 'POST',
                    body: formData,
                });
                const json = await resp.json();

                if (!json.success) {
                    extractStatus.className = 'extract-status extract-status--error';
                    setExtractStatus('bx bx-error-circle', json.error, true);
                    return;
                }

                fillForm(json.data);

                if (json.temp_filename) {
                    extractedFilenameInput.value = json.temp_filename;
                }

                extractStatus.className = 'extract-status extract-status--success';
                setExtractStatus('bx bx-check-circle',
                    `Fields pre-filled from ${file.name}. Review everything below before submitting.`, true);
            } catch (err) {
                extractStatus.className = 'extract-status extract-status--error';
                setExtractStatus('bx bx-error-circle', 'Extraction failed: ' + err.message, true);
            }
        });
    }

    function fillForm(d) {
        // A late create-upload response must not overwrite an opened edit.
        if (document.getElementById('field-capstone-id').value) return;
        // A replacement extraction supplies names, never account identities.
        for (let i = 0; i < 4; i += 1) {
            setField(`authors-${i}-author_id`, '');
            setField(`authors-${i}-user_id`, 0);
            setField(`authors-${i}-first_name`, '');
            setField(`authors-${i}-middle_name`, '');
            setField(`authors-${i}-last_name`, '');
        }
        setField('adviser-author_id', '');
        if (d.title)
            setField('capstone_title', toTitleCase(d.title));

        if (d.year)
            setField('capstone_year', d.year);

        if (d.program)
            fuzzySelectMatch('program_id', d.program);

        if (d.specialization)
            fuzzySelectMatch('specialization_id', d.specialization);

        if (d.keywords && d.keywords.length) {
            const joined = d.keywords.join(', ');
            setField('capstone_keywords', joined);
            renderKeywordChips(d.keywords);
        }

        if (d.authors && d.authors.length) {
            d.authors.forEach((author, i) => {
                setField(`authors-${i}-first_name`, author.first || '');
                setField(`authors-${i}-middle_name`, author.middle || '');
                setField(`authors-${i}-last_name`, author.last || '');
            });
        }

        if (d.adviser) {
            setField('adviser-first_name', d.adviser.first || '');
            setField('adviser-middle_name', d.adviser.middle || '');
            setField('adviser-last_name', d.adviser.last || '');
        }
    }

    function setField(id, value) {
        const el = document.getElementById(id);
        if (el && value !== undefined && value !== null) el.value = value;
    }

    function fuzzySelectMatch(selectId, extracted) {
        const select = document.getElementById(selectId);
        if (!select || !extracted) return;

        const needle = extracted.toLowerCase();
        let bestOption = null;
        let bestScore = 0;

        for (const opt of select.options) {
            if (!opt.value) continue;
            const haystack = opt.text.toLowerCase();
            const score = needle.split(/\s+/).filter(w => w.length > 3 && haystack.includes(w)).length;

            if (score > bestScore) {
                bestScore = score;
                bestOption = opt;
            }
        }

        if (bestOption && bestScore > 0)
            bestOption.selected = true;
    }

    function renderKeywordChips(keywords) {
        const container = document.getElementById('keyword-chips');
        const list = document.getElementById('keyword-chips-list');
        if (!container || !list) return;

        list.replaceChildren();
        keywords.forEach(kw => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'keyword-chip';
            btn.textContent = `+ ${kw}`;
            btn.addEventListener('click', () => {
                const field = document.getElementById('capstone_keywords');
                const current = field.value.trim();
                if (!current.toLowerCase().includes(kw.toLowerCase())) {
                    field.value = current ? `${current}, ${kw}` : kw;
                }
                btn.disabled = true;
                btn.classList.add('keyword-chip--added');
                btn.textContent = `✓ ${kw}`;
            });
            list.appendChild(btn);
        });

        container.style.display = 'block';
    }

    function toTitleCase(str) {
        if (str === str.toUpperCase()) {
            return str.toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
        }
        return str;
    }
});
