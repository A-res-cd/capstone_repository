document.addEventListener('DOMContentLoaded', () => {
    if (typeof Chart === 'undefined' || !window.chartData) {
        return;
    }

    const styles = getComputedStyle(document.documentElement);
    const primary = styles.getPropertyValue('--color-primary').trim() || '#2E3F92';
    const primaryLight = styles.getPropertyValue('--color-primary-light').trim() || '#4A5ED1';
    const accent = styles.getPropertyValue('--color-accent').trim() || '#F39C12';
    const gray = styles.getPropertyValue('--color-gray-light').trim() || '#E5E7EB';
    const palette = [primary, primaryLight, accent, gray, '#3B82F6', '#10B981', '#F97316'];

    const byProgramCanvas = document.getElementById('chart-by-program');
    if (byProgramCanvas && Array.isArray(window.chartData.program_labels)) {
        byProgramCanvas.style.height = '320px';

        new Chart(byProgramCanvas, {
            type: 'doughnut',
            data: {
                labels: window.chartData.program_labels,
                datasets: [{
                    label: 'Capstones',
                    data: window.chartData.program_totals || [],
                    backgroundColor: window.chartData.program_labels.map((_, index) => palette[index % palette.length]),
                    borderWidth: 1,
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
    }

    const byStatusCanvas = document.getElementById('chart-by-status');
    if (byStatusCanvas && Array.isArray(window.chartData.status_labels)) {
        const statusColors = {
            Pending: accent,
            Approved: '#2ecc71',
            Rejected: '#e74c3c',
            Cancelled: gray
        };
        const labels = window.chartData.status_labels;

        byStatusCanvas.style.height = '320px';
        new Chart(byStatusCanvas, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: window.chartData.status_totals || [],
                    backgroundColor: labels.map(label => statusColors[label] || primaryLight),
                    borderWidth: 0,
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
    }
});
