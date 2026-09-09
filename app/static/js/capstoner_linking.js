/* Name matches are search suggestions, never proof of authorship. */
(function () {
    const tokens = (name) => String(name || '').normalize('NFKD')
        .replace(/\p{M}/gu, '').toLocaleLowerCase().match(/[\p{L}\p{N}]+/gu) || [];

    document.querySelectorAll('[data-author-link-form]').forEach((form) => {
        if (form.dataset.authorLinkBound) return;
        form.dataset.authorLinkBound = 'true';
        const account = form.querySelector('[name="user_id"]');
        const credit = form.querySelector('[name="credit"]');
        const confirmed = form.querySelector('[name="confirmed"]');
        const showAll = form.querySelector('[data-show-all-credits]');
        const controls = form.querySelector('[data-author-filter-controls]');
        const status = form.querySelector('#author-match-status');
        const options = Array.from(credit.options).filter((option) => option.value);

        function filter(initial = false) {
            const name = account.selectedOptions[0]?.dataset.accountName || '';
            const parts = tokens(name);
            // Ignore middle initials and name order; retain all same-name credits.
            const matches = options.filter((option) => {
                const author = tokens(option.dataset.authorName);
                return parts.length && author.includes(parts[0]) && author.includes(parts[parts.length - 1]);
            });
            if (initial && credit.value && !matches.some((option) => option.value === credit.value)) showAll.checked = true;
            const filtering = parts.length && !showAll.checked;
            for (const option of options) option.hidden = Boolean(filtering && !matches.includes(option));
            if (credit.selectedOptions[0]?.hidden) {
                credit.value = '';
                confirmed.checked = false;
            }
            status.textContent = !parts.length
                ? 'Choose a user account to narrow the list by author name.'
                : showAll.checked
                    ? `Showing all ${options.length} unlinked author credits. Search by author name or capstone title.`
                    : `${matches.length} matching author ${matches.length === 1 ? 'credit' : 'credits'} for ${name}. ${matches.length ? 'Verify the capstone title, year and credit ID; a matching name is not proof of authorship.' : 'Use “Show all” to search spelling variations or a capstone title.'}`;
            window.CAPRE?.syncSelect?.(credit);
        }

        controls.hidden = false;
        account.addEventListener('change', () => {
            credit.value = '';
            confirmed.checked = false;
            showAll.checked = false;
            filter();
        });
        credit.addEventListener('change', () => { confirmed.checked = false; });
        showAll.addEventListener('change', () => filter());
        form.addEventListener('reset', () => window.setTimeout(() => filter(true), 0));
        filter(true);
    });
})();
