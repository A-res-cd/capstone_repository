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
    const panelList = document.getElementById('panel-list');
    const panelForm = document.getElementById('panel-form');
    const btnOpenCreate = document.getElementById('btn-open-create');
    const btnCloseForm = document.getElementById('btn-close-form');
    const btnCancel = document.getElementById('btn-cancel');

    function openCreate() {
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
        showForm();
    }
    // exposed on window: repository.html calls this from an inline onclick="" attribute
    window.openCreate = openCreate;

    function openEdit(btn) {
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
    }

    function setText(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    }

    function setDisplay(id, value) {
        const el = document.getElementById(id);
        if (el) el.style.display = value;
    }

    function showForm() {
        panelList.classList.add('repo-panel--hidden');
        panelForm.classList.remove('repo-panel--hidden');
        panelForm.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function showList() {
        panelForm.classList.add('repo-panel--hidden');
        panelList.classList.remove('repo-panel--hidden');
    }

    btnOpenCreate.addEventListener('click', openCreate);
    btnCloseForm.addEventListener('click', showList);
    btnCancel.addEventListener('click', showList);

    // Wire up all Edit buttons
    document.querySelectorAll('.btn-row--edit').forEach(btn => {
        btn.addEventListener('click', () => openEdit(btn));
    });

    const extractInput = document.getElementById('extract-file-input');
    const extractStatus = document.getElementById('extract-status');
    const extractedFilenameInput = document.getElementById('extracted-filename');

    if (extractInput) {
        extractInput.addEventListener('change', async () => {
            const file = extractInput.files[0];
            if (!file) return;

            extractStatus.style.display = 'block';
            extractStatus.className = 'extract-status extract-status--loading';
            extractStatus.innerHTML = '<i class="bx bx-loader-alt bx-spin"></i> Reading PDF...';

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
                    extractStatus.innerHTML = `<i class="bx bx-error-circle"></i> ${json.error}`;
                    return;
                }

                fillForm(json.data);

                if (json.temp_filename) {
                    extractedFilenameInput.value = json.temp_filename;
                }

                extractStatus.className = 'extract-status extract-status--success';
                extractStatus.innerHTML = `<i class="bx bx-check-circle"></i>
                    Fields pre-filled from <strong>${file.name}</strong>.
                    Review everything below before submitting.`;
            } catch (err) {
                extractStatus.className = 'extract-status extract-status--error';
                extractStatus.innerHTML = `<i class="bx bx-error-circle"></i> Extraction failed: ${err.message}`;
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
                const n = i + 1;
                setField(`author_first_${n}`, author.first || '');
                setField(`author_middle_${n}`, author.middle || '');
                setField(`author_last_${n}`, author.last || '');
            });
        }

        if (d.adviser) {
            setField('adviser_first', d.adviser.first || '');
            setField('adviser_middle', d.adviser.middle || '');
            setField('adviser_last', d.adviser.last || '');
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
