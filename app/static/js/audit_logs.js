(function () {
    const page = document.querySelector('.audit-page');
    if (!page || page.dataset.bound) return;
    page.dataset.bound = 'true';
    page.addEventListener('click', (event) => {
        const open = event.target.closest('[data-audit-open]');
        if (open) page.querySelector(`#${open.dataset.auditOpen}`)?.showModal();
        const close = event.target.closest('[data-audit-close]');
        if (close) close.closest('dialog').close();
    });
})();
