document.addEventListener('DOMContentLoaded', () => {
    const upload = document.getElementById('cor');
    if (!upload) return;

    const status = document.getElementById('cor-extraction-status');
    const result = document.getElementById('cor-extraction');
    const fields = {
        registration_no: document.getElementById('registration_no'),
        student_no: document.getElementById('student_no'),
        first_name: document.getElementById('first_name'),
        middle_name: document.getElementById('middle_name'),
        last_name: document.getElementById('last_name'),
    };

    upload.addEventListener('change', async () => {
        const file = upload.files[0];
        if (!file) return;

        status.textContent = 'Reading COR details...';
        status.className = 'cor-extraction-status';
        result.hidden = false;

        const data = new FormData();
        data.append('cor', file);
        try {
            const response = await fetch(upload.dataset.extractUrl, {
                method: 'POST',
                body: data,
                headers: {'X-CSRFToken': document.querySelector('input[name="csrf_token"]')?.value || ''},
            });
            const responseText = await response.text();
            let extracted = {};
            try {
                extracted = responseText ? JSON.parse(responseText) : {};
            } catch {
                throw new Error(`The extraction service returned an invalid response (${response.status}).`);
            }
            if (!response.ok) throw new Error(extracted.error || `Could not read this COR (${response.status}).`);

            Object.entries(fields).forEach(([key, field]) => {
                if (field && extracted[key]) field.value = extracted[key];
            });
            status.textContent = extracted.warning || 'COR details found. Check the fields before creating your account.';
            status.classList.add(extracted.warning ? 'is-warning' : 'is-success');
        } catch (error) {
            status.textContent = `${error.message} You may enter the fields manually.`;
            status.classList.add('is-warning');
        }
    });
});
