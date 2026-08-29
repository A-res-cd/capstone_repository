document.addEventListener('DOMContentLoaded', () => {
    function confirmDelete(id, endpoint = '/delete_capstone/', promptText = 'Delete this capstone? This cannot be undone.') {
        if (!confirm(promptText)) return;
        const token = document.querySelector('meta[name="csrf-token"]')?.content;
        const f = document.createElement('form');
        f.method = 'POST';
        f.action = endpoint + id;
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
    // exposed on window: repository.html calls this from an inline onclick="" attribute
    window.confirmDelete = confirmDelete;

    // ── Panel switching ─────────────────────────────────────
    const panelForm = document.getElementById('panel-form');
    const btnOpenCreate = document.getElementById('btn-open-create');
    const btnCloseForm = document.getElementById('btn-close-form');
    const btnCancel = document.getElementById('btn-cancel');
    let preserveCreateDraft = false;

    // Recycle Bin reuses confirmDelete but has no repository form panel.
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

        const id = btn.dataset.id;
        const title = btn.dataset.title;
        const keywords = btn.dataset.keywords;
        const program = btn.dataset.program;
        const spec = btn.dataset.spec;
        const year = btn.dataset.year;
        const semester = btn.dataset.semester;
        const citations = btn.dataset.citations;
        const file = btn.dataset.file;
        const utilized = btn.dataset.utilized === 'true';
        const presented = btn.dataset.presented === 'true';
        const copyrightRegistered = btn.dataset.copyright === 'true';

        document.getElementById('field-capstone-id').value = id;
        document.getElementById('capstone_title').value = title;
        document.getElementById('capstone_keywords').value = keywords;
        document.getElementById('capstone_year').value = year;
        document.getElementById('citation_count').value = citations || 0;
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
            .then(r => r.json())
            .then(data => {
                if (!data.success) return;
                data.authors.forEach((author, i) => {
                    setField(`authors-${i}-first_name`, author.first || '');
                    setField(`authors-${i}-middle_name`, author.middle || '');
                    setField(`authors-${i}-last_name`, author.last || '');
                });
                if (data.adviser) {
                    setField('adviser-first_name', data.adviser.first || '');
                    setField('adviser-middle_name', data.adviser.middle || '');
                    setField('adviser-last_name', data.adviser.last || '');
                }
            })
            .catch(err => console.error('Failed to load capstone authors/adviser:', err));

        showForm();
    }

    function setSelect(id, value) {
        const sel = document.getElementById(id);
        for (let opt of sel.options) {
            if (opt.value == value) { opt.selected = true; break; }
        }
    }

    function resetForm() {
        document.getElementById('capstone-form').reset();
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
    // literal + innerHTML — the icon class is always ours (safe), but the
    // message text may contain a filename or server text we don't fully
    // control, so it's inserted as a text node, never as raw HTML.
    function setExtractStatus(iconClass, message, dismissible = false) {
        extractStatus.innerHTML = '';
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

        list.innerHTML = '';
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
