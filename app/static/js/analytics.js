/* app/static/js/analytics.js
 *
 * Drag-and-drop chart dashboard for the Analytics page.
 *
 * - WIDGET_TYPES registers each available chart (id, label, icon, render fn).
 * - Empty slots show an "Add a chart" picker listing widgets not already placed.
 * - Filled slots are draggable (native HTML5 DnD) and swap places on drop.
 * - Layout (which widget sits in which slot) persists in localStorage so it
 *   survives a page reload. No backend/DB change needed.
 */
document.addEventListener('DOMContentLoaded', () => {

    const STORAGE_KEY = 'capre_analytics_layout';
    const grid = document.getElementById('analytics-grid');

    if (!grid) return;

    if (typeof Chart === 'undefined') {
        console.error('[analytics.js] Chart.js not loaded — charts will not render.');
        return;
    }
    if (!window.chartData) {
        console.error('[analytics.js] window.chartData not set — no data to render.');
        return;
    }

    const styles       = getComputedStyle(document.documentElement);
    const primary      = styles.getPropertyValue('--color-primary').trim()       || '#2E3F92';
    const primaryLight = styles.getPropertyValue('--color-primary-light').trim() || '#4A5ED1';
    const accent       = styles.getPropertyValue('--color-accent').trim()        || '#F39C12';
    const grayLight    = styles.getPropertyValue('--color-gray-light').trim()    || '#E5E7EB';

    // ── Widget registry ─────────────────────────────────────────────────
    const WIDGET_TYPES = {
        'by-specialization': {
            label: 'Capstones by Specialization',
            icon: 'bx-bar-chart-alt-2',
            render(canvas) {
                const labels = window.chartData.specialization_labels || [];
                if (!labels.length) return false;
                const specializationColors = { 'DST': '#92422e', 'WST': '#4A5ED1', 'NST': '#F39C12' };
                new Chart(canvas, {
                    type: 'bar',
                    data: {
                        labels,
                        datasets: [{
                            label: 'Capstones',
                            data: window.chartData.specialization_totals,
                            backgroundColor: labels.map(l => specializationColors[l] || primaryLight)
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { position: 'bottom' } }
                    }
                });
                return true;
            }
        },
        'by-status': {
            label: 'Requests by Status',
            icon: 'bx-donut-chart',
            render(canvas) {
                const labels = window.chartData.status_labels || [];
                if (!labels.length) return false;
                const statusColors = {
                    'Pending': accent, 'Approved': '#2ecc71',
                    'Rejected': '#e74c3c', 'Cancelled': grayLight,
                };
                new Chart(canvas, {
                    type: 'doughnut',
                    data: {
                        labels,
                        datasets: [{
                            data: window.chartData.status_totals,
                            backgroundColor: labels.map(l => statusColors[l] || primaryLight),
                            borderWidth: 0,
                            hoverOffset: 8,
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        onClick: (event, elements) => {
                            if (elements.length === 0) return;
                            const status = labels[elements[0].index];
                            window.location.href = `/requests?status=${encodeURIComponent(status)}`;
                        },
                        plugins: {
                            tooltip: {
                                callbacks: {
                                    label: (ctx) => `${ctx.label}: ${ctx.raw}. Click to view requests`
                                }
                            },
                            legend: { position: 'bottom' }
                        }
                    }
                });
                return true;
            }
        }
    };

    const slots = Array.from(grid.querySelectorAll('.analytics-widget-slot'));
    let layout = loadLayout();

    // ── Persistence ──────────────────────────────────────────────────────
    function loadLayout() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) return {};
            const parsed = JSON.parse(raw);
            return (parsed && typeof parsed === 'object') ? parsed : {};
        } catch (e) {
            console.warn('[analytics.js] Could not read saved layout:', e);
            return {};
        }
    }

    function saveLayout() {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(layout));
        } catch (e) {
            console.warn('[analytics.js] Could not save layout:', e);
        }
    }

    // ── Rendering ────────────────────────────────────────────────────────
    function widgetsInUse() {
        return new Set(Object.values(layout).filter(Boolean));
    }

    function renderSlot(slot) {
        const slotId = slot.dataset.slot;
        const widgetId = layout[slotId];

        slot.innerHTML = '';
        slot.removeAttribute('draggable');
        slot.classList.remove('analytics-widget-slot--filled');

        if (!widgetId || !WIDGET_TYPES[widgetId]) {
            renderEmptySlot(slot);
            return;
        }

        const widget = WIDGET_TYPES[widgetId];
        slot.classList.add('analytics-widget-slot--filled');
        slot.setAttribute('draggable', 'true');

        const tab = document.createElement('span');
        tab.className = 'analytics-widget__tab';
        tab.textContent = widget.label;
        slot.appendChild(tab);

        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'analytics-widget__remove';
        removeBtn.setAttribute('aria-label', `Remove ${widget.label}`);
        removeBtn.innerHTML = '<i class="bx bx-x"></i>';
        removeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            delete layout[slotId];
            saveLayout();
            renderSlot(slot);
        });
        slot.appendChild(removeBtn);

        const canvasWrap = document.createElement('div');
        canvasWrap.className = 'analytics-widget__canvas-wrap';
        const canvas = document.createElement('canvas');
        canvasWrap.appendChild(canvas);
        slot.appendChild(canvasWrap);

        const ok = widget.render(canvas);
        if (!ok) {
            canvasWrap.innerHTML = '<p class="analytics-widget__empty-msg">No data available.</p>';
        }
    }

    function renderEmptySlot(slot) {
        const slotId = slot.dataset.slot;

        const prompt = document.createElement('button');
        prompt.type = 'button';
        prompt.className = 'analytics-widget-slot__prompt';
        prompt.innerHTML = '<i class="bx bx-plus-circle"></i><span>Add a chart</span>';
        slot.appendChild(prompt);

        prompt.addEventListener('click', () => openPicker(slot, slotId));
    }

    function openPicker(slot, slotId) {
        closeAnyOpenPicker();

        const used = widgetsInUse();
        const available = Object.entries(WIDGET_TYPES).filter(([id]) => !used.has(id));

        const picker = document.createElement('div');
        picker.className = 'analytics-widget-picker';

        if (!available.length) {
            picker.innerHTML = '<p class="analytics-widget-picker__empty">All charts already placed.</p>';
        } else {
            available.forEach(([id, widget]) => {
                const item = document.createElement('button');
                item.type = 'button';
                item.className = 'analytics-widget-picker__item';
                item.innerHTML = `<i class="bx ${widget.icon}"></i><span>${widget.label}</span>`;
                item.addEventListener('click', () => {
                    layout[slotId] = id;
                    saveLayout();
                    closeAnyOpenPicker();
                    renderSlot(slot);
                });
                picker.appendChild(item);
            });
        }

        slot.appendChild(picker);

        // Close picker on outside click.
        setTimeout(() => {
            document.addEventListener('click', onOutsideClick);
        }, 0);

        function onOutsideClick(e) {
            if (!picker.contains(e.target)) {
                closeAnyOpenPicker();
            }
        }

        function closeAnyOpenPicker() {
            document.querySelectorAll('.analytics-widget-picker').forEach(p => p.remove());
            document.removeEventListener('click', onOutsideClick);
        }
    }

    function closeAnyOpenPicker() {
        document.querySelectorAll('.analytics-widget-picker').forEach(p => p.remove());
    }

    // ── Drag and drop (swap two slots' contents) ────────────────────────
    let dragSourceId = null;

    slots.forEach(slot => {
        slot.addEventListener('dragstart', (e) => {
            if (!slot.classList.contains('analytics-widget-slot--filled')) {
                e.preventDefault();
                return;
            }
            dragSourceId = slot.dataset.slot;
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', dragSourceId);
            slot.classList.add('analytics-widget-slot--dragging');
        });

        slot.addEventListener('dragend', () => {
            slot.classList.remove('analytics-widget-slot--dragging');
            slots.forEach(s => s.classList.remove('analytics-widget-slot--dragover'));
        });

        slot.addEventListener('dragover', (e) => {
            if (!dragSourceId) return;
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            slot.classList.add('analytics-widget-slot--dragover');
        });

        slot.addEventListener('dragleave', () => {
            slot.classList.remove('analytics-widget-slot--dragover');
        });

        slot.addEventListener('drop', (e) => {
            e.preventDefault();
            slot.classList.remove('analytics-widget-slot--dragover');

            const targetId = slot.dataset.slot;
            if (!dragSourceId || dragSourceId === targetId) return;

            const sourceWidget = layout[dragSourceId];
            const targetWidget = layout[targetId];

            if (targetWidget) {
                layout[dragSourceId] = targetWidget;
            } else {
                delete layout[dragSourceId];
            }
            layout[targetId] = sourceWidget;

            saveLayout();
            dragSourceId = null;

            slots.forEach(renderSlot);
        });
    });

    // ── Initial render ───────────────────────────────────────────────────
    slots.forEach(renderSlot);
});
