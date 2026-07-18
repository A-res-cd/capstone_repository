document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.request-row').forEach(row => {
        row.addEventListener('click', () => {

            document.querySelectorAll('.request-row').forEach(r => r.classList.remove('active'));
            row.classList.add('active');

            const requestId = row.dataset.requestId;
            const requester = row.dataset.requester;
            const capstone = row.dataset.capstone;
            const reason = row.dataset.reason;
            const status = row.dataset.status;
            const feedback = row.dataset.feedback;
            const date = row.dataset.date;

            document.getElementById('sidebar-empty').style.display = 'none';
            document.getElementById('sidebar-detail').style.display = 'flex';

            document.getElementById('sd-requester').textContent = requester;
            document.getElementById('sd-capstone').textContent = capstone;
            document.getElementById('sd-date').textContent = date;
            const statusEl = document.getElementById('sd-status');
            statusEl.textContent = status.charAt(0).toUpperCase() + status.slice(1);
            statusEl.className = `status-badge status-badge--${status}`;
            document.getElementById('sd-reason').textContent = reason;

            const actionForm = document.getElementById('sd-action-form');
            const alreadyDecided = document.getElementById('sd-already-decided');
            const decideForm = document.getElementById('decide-form');

            if (decideForm) {
                decideForm.action = BASE_DECIDE_URL.slice(0, BASE_DECIDE_URL.lastIndexOf('/')) + '/' + requestId;
            }

            if (status === 'pending') {
                actionForm.style.display = 'block';
                alreadyDecided.style.display = 'none';
                const statusReasonInput = document.getElementById('status_reason');
                if (statusReasonInput) statusReasonInput.value = '';
            } else {
                actionForm.style.display = 'none';
                alreadyDecided.style.display = 'block';
                document.getElementById('sd-feedback').textContent = feedback || '—';
            }
        });
    });
});