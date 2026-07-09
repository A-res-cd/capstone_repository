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


    // ── Chart 1: Capstones by Specialization (BAR) ─────────────────────────────────
    const bySpecializationCanvas = document.getElementById('chart-by-specialization');
    if (bySpecializationCanvas && window.chartData.specialization_labels?.length) {
        const specializationColors = {
            'Database Systems Technology': '#2E3F92',
            'Web Systems Technology': '#4A5ED1',
            'Network Systems Technology': '#F39C12',
        }

        try {
            new Chart(bySpecializationCanvas, {
                type: 'bar',

                data: {
                    labels: window.chartData.specialization_labels,
                    datasets: [{
                        label: 'Capstones',
                        data: window.chartData.specialization_totals
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: 'bottom' }
                    }
                }
            });
        } catch (e) {
            console.error(e);
        }
    } else {
        console.warn('[analytics.js] #chart-by-specialization canvas not found or no data.');
    }

    // ── Chart 2: Requests by Status (DOUGHNUT) ──────────────────────────────
    const byStatusCanvas = document.getElementById('chart-by-status');
    if (byStatusCanvas && window.chartData.status_labels?.length) {
        const statusColors = {
            'Pending':   accent,
            'Approved':  '#2ecc71',
            'Rejected':  '#e74c3c',
            'Cancelled': grayLight,
        };
        const labels = window.chartData.status_labels;

        new Chart(byStatusCanvas, {
            type: 'doughnut',
            data: {
                labels: labels,
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
                plugins: {
                    legend: { position: 'bottom' }
                }
            }
        });
    } else {
        console.warn('[analytics.js] #chart-by-status canvas not found or no data.');
    }

});