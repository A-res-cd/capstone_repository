/* app/static/js/analytics.js
 *
 * Fixed-layout chart dashboard for the Analytics page, styled after the
 * CICT reference dashboard: stat cards, a per-specialization trend line chart,
 * a requests-by-status donut + top-cited list sidebar, and a program
 * donut + summary table along the bottom.
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

    // Shared palette — used for both the trend lines and the program
    // donut, so a given program keeps the same color across the page.
    const PALETTE = [primary, '#27AE60', accent, '#1E96A3', '#7C56D1', '#B23A28'];
    const colorFor = (i) => PALETTE[i % PALETTE.length];

    function showEmpty(canvas, message) {
        const wrap = canvas.closest('.analytics-panel__chart-wrap');
        if (wrap) wrap.innerHTML = `<p class="analytics-widget__empty-msg">${message}</p>`;
    }

    // ── Capstone Trend per Year (multi-line) ───────────────────────────
    const trendCanvas = document.getElementById('trend-chart');
    if (trendCanvas) {
        const years = window.chartData.trend_years || [];
        const series = window.chartData.trend_series || {};
        const specializations = Object.keys(series);

        if (!years.length || !specializations.length) {
            showEmpty(trendCanvas, 'No capstone data available yet.');
        } else {
            // Y-axis: starts at 0, base ceiling of 50 stepping by 10. If the
            // highest value in any series exceeds the current ceiling, bump
            // the ceiling by another 50 (100, 150, ...) — step stays fixed
            // at 10 the whole way up.
            const dataMax = Math.max(0, ...specializations.flatMap(p => series[p]));
            let axisMax = 50;
            while (dataMax > axisMax) axisMax += 50;
            const axisStep = 10;

            new Chart(trendCanvas, {
                type: 'line',
                data: {
                    labels: years,
                    datasets: specializations.map((specialization, i) => ({
                        label: specialization,
                        data: series[specialization],
                        borderColor: colorFor(i),
                        backgroundColor: colorFor(i),
                        pointRadius: 3,
                        pointHoverRadius: 5,
                        tension: 0.35,
                        fill: false,
                    })),
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    plugins: {
                        legend: { position: 'top', labels: { boxWidth: 10, font: { size: 11 } } },
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            min: 0,
                            max: axisMax,
                            ticks: { stepSize: axisStep },
                            grid: { color: grayLight },
                        },
                        x: { grid: { display: false } },
                    },
                },
            });
        }
    }

    // ── Total Capstone by Program (donut) ──────────────────────────────
    const programCanvas = document.getElementById('program-chart');
    if (programCanvas) {
        const labels = window.chartData.program_labels || [];
        if (!labels.length) {
            showEmpty(programCanvas, 'No program data available.');
        } else {
            new Chart(programCanvas, {
                type: 'doughnut',
                data: {
                    labels,
                    datasets: [{
                        data: window.chartData.program_totals,
                        backgroundColor: labels.map((_, i) => colorFor(i)),
                        borderWidth: 0,
                        hoverOffset: 6,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '62%',
                    plugins: {
                        legend: { position: 'right', labels: { boxWidth: 10, font: { size: 11 } } },
                    },
                },
            });
        }
    }

    // ── Requests by Status (donut) ─────────────────────────────────────
    const statusCanvas = document.getElementById('status-chart');
    if (statusCanvas) {
        const labels = window.chartData.status_labels || [];
        if (!labels.length) {
            showEmpty(statusCanvas, 'No data available.');
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
