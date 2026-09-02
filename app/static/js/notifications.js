document.addEventListener('DOMContentLoaded', () => {
    const menu = document.getElementById('notification-menu');
    const toggle = document.getElementById('notification-toggle');
    const panel = document.getElementById('notification-panel');
    const markRead = document.getElementById('notifications-mark-read');

    if (!menu || !toggle || !panel) return;

    const close = () => {
        panel.hidden = true;
        toggle.setAttribute('aria-expanded', 'false');
    };

    toggle.addEventListener('click', () => {
        const willOpen = panel.hidden;
        panel.hidden = !willOpen;
        toggle.setAttribute('aria-expanded', String(willOpen));
    });

    document.addEventListener('click', (event) => {
        if (!menu.contains(event.target)) close();
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            close();
            toggle.focus();
        }
    });

    if (markRead) {
        markRead.addEventListener('click', async () => {
            markRead.disabled = true;
            try {
                const response = await fetch('/notifications/read', {
                    method: 'POST',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content,
                    },
                });
                if (!response.ok) throw new Error('Request failed');

                menu.querySelector('.notification-badge')?.remove();
                menu.querySelectorAll('.notification-item.is-unread').forEach((item) => {
                    item.classList.remove('is-unread');
                });
                markRead.remove();
                toggle.setAttribute('aria-label', 'Notifications');
            } catch (error) {
                markRead.disabled = false;
            }
        });
    }
});
