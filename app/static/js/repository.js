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
        document.getElementById('file-label-note').textContent = '(required)';
        document.getElementById('current-file-note').textContent = '';
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

        document.getElementById('field-capstone-id').value = id;
        document.getElementById('capstone_title').value = title;
        document.getElementById('capstone_keywords').value = keywords;
        document.getElementById('capstone_year').value = year;
        document.getElementById('citation_count').value = citations || 0;

        // select dropdowns
        setSelect('program_id', program);
        setSelect('specialization_id', spec);
        setSelect('semester', semester);

        document.getElementById('form-heading').textContent = 'Edit Capstone';
        document.getElementById('form-subheading').textContent = 'Update the details for this capstone record.';
        document.getElementById('btn-submit-label').textContent = 'Save Changes';
        document.getElementById('file-label-note').textContent = '(leave blank to keep existing)';
        document.getElementById('current-file-note').textContent =
            file ? ' · Current: ' + file : ' · No file uploaded';

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
});