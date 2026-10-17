document.addEventListener('DOMContentLoaded', () => {
    const upload = document.getElementById('cor');
    if (!upload) return;

    const status = document.getElementById('cor-extraction-status');
    const role = document.getElementById('role');
    const result = document.getElementById('cor-extraction');
    const fields = {
        student_no: document.getElementById('student_no'),
        first_name: document.getElementById('first_name'),
        middle_name: document.getElementById('middle_name'),
        last_name: document.getElementById('last_name'),
    };
    let extraction = 0;
    let controller;

    function updateDocumentType() {
        const faculty = role.value === 'Faculty';
        upload.accept = faculty ? '.jpg,.jpeg,.png,image/jpeg,image/png' : '.pdf,application/pdf';
        fields.student_no.required = faculty;
        if (faculty) fields.student_no.pattern = '[0-9]{3,4}';
        else fields.student_no.removeAttribute('pattern');
        fields.student_no.maxLength = faculty ? 4 : 50;
    }

    async function extract() {
        const requestId = ++extraction;
        controller?.abort();
        const file = upload.files[0];
        upload.dataset.extracting = 'false';
        if (!file) return;
        upload.dataset.extracting = 'true';
        controller = new AbortController();
        const requestController = controller;
        const timeout = setTimeout(() => requestController.abort(), 30000);

        status.textContent = role.value === 'Faculty' ? 'Reading faculty ID...' : 'Reading COR details...';
        status.className = 'cor-extraction-status';
        result.hidden = false;

        const data = new FormData();
        data.append('cor', file);
        data.append('role', role.value);
        try {
            const response = await fetch(upload.dataset.extractUrl, {
                method: 'POST',
                body: data,
                signal: controller.signal,
                headers: {'X-CSRFToken': document.querySelector('input[name="csrf_token"]')?.value || ''},
            });
            const extracted = await response.json();
            if (requestId !== extraction) return;
            if (!response.ok) throw new Error(extracted.error || 'Could not read this document.');

            Object.entries(fields).forEach(([key, field]) => {
                if (field && extracted[key]) field.value = extracted[key];
            });
            status.textContent = extracted.warning || 'Details found. Check the fields before creating your account.';
            status.classList.add(extracted.warning ? 'is-warning' : 'is-success');
        } catch (error) {
            if (requestId !== extraction) return;
            status.textContent = `${error.message} You may enter the fields manually.`;
            status.classList.add('is-warning');
        } finally {
            clearTimeout(timeout);
            if (requestId === extraction) upload.dataset.extracting = 'false';
        }
    }

    upload.addEventListener('change', extract);
    role.addEventListener('change', () => {
        ++extraction;
        controller?.abort();
        upload.value = '';
        upload.dataset.extracting = 'false';
        Object.values(fields).forEach(field => { if (field) field.value = ''; });
        status.textContent = role.value === 'Faculty' ? 'Upload a JPG or PNG image of your faculty ID.' : 'Upload your COR as a PDF.';
        status.className = 'cor-extraction-status';
        result.hidden = false;
        updateDocumentType();
    });
    updateDocumentType();
});
