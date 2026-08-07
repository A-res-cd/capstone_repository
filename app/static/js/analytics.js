/* app/static/js/analytics.js
 *
 * Fixed-layout chart dashboard for the Analytics page.
 *
 * NOTE: drag-and-drop widget slots / the "Add a chart" picker have been
 * temporarily removed in favor of a fixed two-column layout. Charts render
 * straight into #specialization-chart and #status-chart on load.
 */
document.addEventListener('DOMContentLoaded', () => {

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

    // ── Capstones by Specialization (bar) ──────────────────────────────
    const specCanvas = document.getElementById('specialization-chart');
    if (specCanvas) {
        const labels = window.chartData.specialization_labels || [];
        const wrap = specCanvas.closest('.analytics-panel__chart-wrap');
        if (!labels.length) {
            if (wrap) wrap.innerHTML = '<p class="analytics-widget__empty-msg">No data available.</p>';
        } else {
            const specializationColors = { 'DST': '#92422e', 'WST': '#4A5ED1', 'NST': '#F39C12' };
            new Chart(specCanvas, {
                type: 'bar',
                data: {
                    labels,
                    datasets: [{
                        label: 'Capstones',
                        data: window.chartData.specialization_totals,
                        backgroundColor: labels.map(l => specializationColors[l] || primaryLight),
                        borderRadius: 6,
                        maxBarThickness: 48
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        y: { beginAtZero: true, grid: { color: grayLight } },
                        x: { grid: { display: false } }
                    }
                }
            });
        }
    }

    // ── Requests by Status (donut) ─────────────────────────────────────
    const statusCanvas = document.getElementById('status-chart');
    if (statusCanvas) {
        const labels = window.chartData.status_labels || [];
        const wrap = statusCanvas.closest('.analytics-panel__chart-wrap');
        if (!labels.length) {
            if (wrap) wrap.innerHTML = '<p class="analytics-widget__empty-msg">No data available.</p>';
        } else {
            const statusColors = {
                'Pending': accent, 'Approved': '#2ecc71',
                'Rejected': '#e74c3c', 'Cancelled': grayLight,
            };
            new Chart(statusCanvas, {
                type: 'doughnut',
                data: {
                    labels,
                    datasets: [{
                        data: window.chartData.status_totals,
                        backgroundColor: labels.map(l => statusColors[l] || primaryLight),
                        borderWidth: 0,
                        hoverOffset: 6,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '68%',
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
                        legend: { position: 'bottom', labels: { boxWidth: 10, font: { size: 11 } } }
                    }
                }
            });
        }
    }
});
