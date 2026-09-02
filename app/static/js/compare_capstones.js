document.addEventListener('DOMContentLoaded', () => {
    const STORAGE_KEY = 'capre-compare-capstones';
    const tray = document.getElementById('compare-tray');
    const selectedWrap = document.getElementById('compare-selected');
    const status = document.getElementById('compare-status');
    const count = document.getElementById('compare-count');
    const openButton = document.getElementById('compare-open');
    const clearButton = document.getElementById('compare-clear');
    const overlay = document.getElementById('compare-modal-overlay');
    const closeButton = document.getElementById('compare-close');
    const tableWrap = document.getElementById('compare-table-wrap');

    if (!tray || !openButton || !overlay || !tableWrap) return;

    const textFields = ['title', 'program', 'specialization', 'year', 'semester', 'keywords'];

    function normalize(item) {
        if (!item || !/^\d+$/.test(String(item.id))) return null;
        const normalized = { id: String(item.id) };
        textFields.forEach((field) => {
            normalized[field] = String(item[field] || '—').slice(0, 1000);
        });
        return normalized;
    }

    function loadSelected() {
        try {
            const stored = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '[]');
            return Array.isArray(stored) ? stored.map(normalize).filter(Boolean).slice(0, 3) : [];
        } catch (error) {
            return [];
        }
    }

    let selected = loadSelected();

    function cardData(card) {
        return normalize({
            id: card.dataset.id,
            title: card.dataset.title,
            program: card.dataset.program,
            specialization: card.dataset.spec,
            year: card.dataset.year,
            semester: card.dataset.semester,
            keywords: card.dataset.keywords,
        });
    }

    function persist() {
        try {
            sessionStorage.setItem(STORAGE_KEY, JSON.stringify(selected));
        } catch (error) {
            // Comparison still works for this page when storage is unavailable.
        }
    }

    function setCompareButton(button, isSelected) {
        button.classList.toggle('is-selected', isSelected);
        button.setAttribute('aria-pressed', String(isSelected));
        button.setAttribute('aria-label', isSelected ? 'Remove capstone from comparison' : 'Add capstone to comparison');
    }

    function renderTray(message = '') {
        tray.hidden = selected.length === 0;
        count.textContent = `${selected.length}/3`;
        openButton.disabled = selected.length < 2;
        selectedWrap.replaceChildren();
        selected.forEach((item) => {
            const chip = document.createElement('span');
            chip.textContent = item.title;
            chip.title = item.title;
            selectedWrap.appendChild(chip);
        });
        status.textContent = message || (
            selected.length < 2
                ? 'Select one more capstone.'
                : `${selected.length} capstones ready to compare.`
        );

        document.querySelectorAll('.archive-card').forEach((card) => {
            const itemIndex = selected.findIndex((item) => item.id === card.dataset.id);
            if (itemIndex >= 0) selected[itemIndex] = cardData(card);
            const button = card.querySelector('.compare-capstone-btn');
            if (button) setCompareButton(button, itemIndex >= 0);
        });
        persist();
    }

    function toggleCard(card) {
        const item = cardData(card);
        if (!item) return;
        const existingIndex = selected.findIndex((entry) => entry.id === item.id);
        if (existingIndex >= 0) {
            selected.splice(existingIndex, 1);
            renderTray();
            return;
        }
        if (selected.length >= 3) {
            renderTray('Maximum is 3 capstones. Remove one first.');
            return;
        }
        selected.push(item);
        renderTray();
    }

    function renderTable() {
        const fields = [
            ['Year', 'year'],
            ['Program', 'program'],
            ['Specialization', 'specialization'],
            ['Semester', 'semester'],
            ['Keywords', 'keywords'],
        ];
        const table = document.createElement('table');
        table.className = 'compare-table';
        const head = document.createElement('thead');
        const headRow = document.createElement('tr');
        const fieldHead = document.createElement('th');
        fieldHead.scope = 'col';
        fieldHead.textContent = 'Field';
        headRow.appendChild(fieldHead);
        selected.forEach((item) => {
            const titleHead = document.createElement('th');
            titleHead.scope = 'col';
            titleHead.textContent = item.title;
            headRow.appendChild(titleHead);
        });
        head.appendChild(headRow);
        table.appendChild(head);

        const body = document.createElement('tbody');
        fields.forEach(([label, key]) => {
            const row = document.createElement('tr');
            const rowHead = document.createElement('th');
            rowHead.scope = 'row';
            rowHead.textContent = label;
            row.appendChild(rowHead);
            selected.forEach((item) => {
                const cell = document.createElement('td');
                cell.textContent = item[key];
                row.appendChild(cell);
            });
            body.appendChild(row);
        });
        table.appendChild(body);
        tableWrap.replaceChildren(table);
    }

    function closeModal() {
        overlay.hidden = true;
        document.body.classList.remove('compare-modal-open');
    }

    document.querySelectorAll('.compare-capstone-btn').forEach((button) => {
        button.addEventListener('click', (event) => {
            event.stopPropagation();
            toggleCard(button.closest('.archive-card'));
        });
    });

    openButton.addEventListener('click', () => {
        if (selected.length < 2) return;
        renderTable();
        overlay.hidden = false;
        document.body.classList.add('compare-modal-open');
        closeButton.focus();
    });

    clearButton.addEventListener('click', () => {
        selected = [];
        renderTray();
    });
    closeButton.addEventListener('click', closeModal);
    overlay.addEventListener('click', (event) => {
        if (event.target === overlay) closeModal();
    });
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && !overlay.hidden) closeModal();
    });

    renderTray();
});
