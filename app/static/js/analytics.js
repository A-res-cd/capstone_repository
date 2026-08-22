document.addEventListener('DOMContentLoaded', () => {

    if (typeof Chart === 'undefined') {
        console.error('[analytics.js] Chart.js not loaded — charts will not render.');
        return;
    }

    if (!window.chartData) {
        console.error('[analytics.js] window.chartData not set — no data to render.');
        return;
    }


    /* ============================================================
       THEME COLORS
    ============================================================ */

    const getVar = (name, fallback) =>
        getComputedStyle(document.documentElement)
            .getPropertyValue(name).trim() || fallback;

    const getThemeColors = () => ({
        primary: getVar('--color-primary', '#2E3F92'),
        accent: getVar('--color-accent', '#F39C12'),
        grayLight: getVar('--color-gray-light', '#E5E5E5'),
        textDark: getVar('--text-dark', '#333333'),
        borderColor: getVar('--border-color', '#ECE9DD')
    });

    const primary =
        getVar('--color-primary', '#2E3F92');

    const primaryLight =
        getVar('--color-primary-light', '#4A5ED1');

    const accent =
        getVar('--color-accent', '#F39C12');

    const grayLight =
        getVar('--color-gray-light', '#E5E5E5');

    const grayDark =
        getVar('--color-gray-dark', '#4F4F4F');

    const textDark =
        getVar('--text-dark', '#333333');

    const borderColor =
        getVar('--border-color', '#ECE9DD');

    const surfacePaper =
        getVar('--surface-paper', '#FDFCF7');


    /* ============================================================
       SHARED PROGRAM PALETTE
    ============================================================ */

    const PALETTE = [
        primary,
        '#27AE60',
        accent,
        '#1E96A3',
        '#7C56D1',
        '#B23A28'
    ];

    const colorFor = (i) =>
        PALETTE[i % PALETTE.length];

    const charts = {};


    /* ============================================================
       EMPTY CHART
    ============================================================ */

    function showEmpty(canvas, message) {
        const wrap = canvas.closest('.analytics-panel__chart-wrap');

        if (wrap) {
            wrap.innerHTML = `
                <p class="analytics-widget__empty-msg">
                    ${message}
                </p>
            `;
        }
    }


    /* ============================================================
       CENTER TEXT PLUGIN

       Used by the Published / Utilized / Presented /
       Copyright doughnuts.
    ============================================================ */
    const doughnutCenterText = {
        id: 'doughnutCenterText',
        afterDraw(chart, args, pluginOptions) {
            if (!pluginOptions || !pluginOptions.display) {
                return;
            }
            const {
                ctx,
                chartArea: {
                    left,
                    right,
                    top,
                    bottom
                }
            } = chart;

            const dataset = chart.data.datasets[0];

            if (!dataset || !dataset.data) {
                return;
            }

            const values = dataset.data.map(Number);
            const total = values.reduce(
                (sum, value) => sum + value,
                0
            );

            if (!total) {
                return;
            }

            const positiveValue = values[0] || 0;
            const percentage = Math.round(
                (positiveValue / total) * 100
            );
            const centerX = (left + right) / 2;
            const centerY = (top + bottom) / 2;
            const computedStyles =
                getComputedStyle(document.documentElement);
            const textColor =
                computedStyles
                    .getPropertyValue('--text-dark')
                    .trim() || '#333333';
            ctx.save();
            /*
             * Main number
             */
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillStyle = textColor;
            ctx.font = '700 18px "Segoe UI", sans-serif';
            ctx.fillText(
                positiveValue.toLocaleString(),
                centerX,
                centerY - 6
            );
            /*
             * Percentage
             */
            ctx.font = '600 9px "Segoe UI", sans-serif';
            ctx.fillText(
                `${percentage}%`,
                centerX,
                centerY + 11
            );
            ctx.restore();
        }
    };

    Chart.register(doughnutCenterText);


    /* ============================================================
       CAPSTONE TREND PER YEAR
    ============================================================ */

    const trendCanvas =
        document.getElementById('trend-chart');

    if (trendCanvas) {
        const years =
            window.chartData.trend_years || [];
        const series =
            window.chartData.trend_series || {};
        const specializations =
            Object.keys(series);

        if (!years.length || !specializations.length) {
            showEmpty(
                trendCanvas,
                'No capstone data available yet.'
            );
        } else {
            const dataMax =
                Math.max(
                    0,
                    ...specializations.flatMap(
                        p => series[p]
                    )
                );
            let axisMax = 50;
            while (dataMax > axisMax) {
                axisMax += 50;
            }
            const axisStep = 10;
            charts.trend = new Chart(trendCanvas, {
                type: 'line',
                data: {
                    labels: years,
                    datasets: specializations.map(
                        (specialization, i) => ({
                            label: specialization,
                            data:
                                series[specialization],
                            borderColor:
                                colorFor(i),
                            backgroundColor:
                                colorFor(i),
                            pointRadius: 3,
                            pointHoverRadius: 5,
                            tension: 0.35,
                            fill: false
                        })
                    )
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        mode: 'index',
                        intersect: false
                    },
                    plugins: {
                        legend: {
                            position: 'top',
                            labels: {
                                color: textDark,
                                boxWidth: 10,
                                padding: 10,
                                font: {
                                    size: 11
                                }
                            }
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            min: 0,
                            max: axisMax,
                            ticks: {
                                stepSize: axisStep,
                                color: textDark
                            },
                            grid: {
                                color: borderColor
                            }
                        },
                        x: {
                            ticks: {
                                color: textDark
                            },
                            grid: {
                                display: false
                            }
                        }
                    }
                }
            });
        }
    }

    /* ============================================================
       TOTAL CAPSTONE BY PROGRAM
    ============================================================ */
    const programCanvas =
        document.getElementById('program-chart');
    if (programCanvas) {
        const labels =
            window.chartData.program_labels || [];

        if (!labels.length) {
            showEmpty(
                programCanvas,
                'No program data available.'
            );
        } else {
            charts.program = new Chart(programCanvas, {
                type: 'doughnut',
                data: {
                    labels,
                    datasets: [{
                        data:
                            window.chartData.program_totals,
                        backgroundColor:
                            labels.map(
                                (_, i) => colorFor(i)
                            ),
                        borderWidth: 0,
                        hoverOffset: 6
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '62%',
                    plugins: {
                        legend: {
                            position: 'right',
                            align: 'center',
                            labels: {
                                color: textDark,
                                boxWidth: 8,
                                boxHeight: 8,
                                padding: 8,
                                font: {
                                    size: 10
                                }
                            }
                        }
                    }
                }
            });
        }
    }


    /* ============================================================
       STATUS DOUGHNUTS

       Published
       Utilized
       Presented
       Copyright Registered
    ============================================================ */

    function renderStatusDonut(
        canvasId,
        labels,
        totals,
        yesColor
    ) {

        const canvas =
            document.getElementById(canvasId);

        if (!canvas) {
            return;
        }

        const values =
            (totals || []).map(Number);

        const total =
            values.reduce(
                (a, b) => a + b,
                0
            );

        if (!total) {
            showEmpty(
                canvas,
                'No data available.'
            );
            return;
        }
        /*
         * Neutral "No" color.
         *
         * Uses the dark/light theme's gray-light variable.
         */
        const noColor = grayLight;

        charts[canvasId] = new Chart(canvas, {
            type: 'doughnut',
            data: {
                labels,
                datasets: [{
                    data: values,
                    backgroundColor: [
                        yesColor,
                        noColor
                    ],
                    borderWidth: 0,
                    hoverOffset: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '68%',
                animation: {
                    duration: 500
                },
                plugins: {
                    /*
                     * Reference-style center number.
                     */
                    doughnutCenterText: {
                        display: true
                    },
                    legend: {
                        display: true,
                        position: 'right',
                        align: 'center',
                        labels: {
                            color: textDark,
                            boxWidth: 8,
                            boxHeight: 8,
                            padding: 6,
                            usePointStyle: false,
                            font: {
                                size: 9
                            }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const value =
                                    context.raw || 0;
                                const percentage =
                                    Math.round(
                                        (value / total) * 100
                                    );
                                return `${context.label}: ${value} (${percentage}%)`;
                            }
                        }
                    }
                }
            }
        });
    }


    /* ============================================================
       RENDER STATUS CHARTS
    ============================================================ */

    renderStatusDonut(
        'published-chart',
        window.chartData.published_labels,
        window.chartData.published_totals,
        primary
    );


    renderStatusDonut(
        'utilized-chart',
        window.chartData.utilized_labels,
        window.chartData.utilized_totals,
        '#27AE60'
    );


    renderStatusDonut(
        'presented-chart',
        window.chartData.presented_labels,
        window.chartData.presented_totals,
        accent
    );


    renderStatusDonut(
        'copyright-chart',
        window.chartData.copyright_labels,
        window.chartData.copyright_totals,
        '#7C56D1'
    );

    document.addEventListener('themechange', () => {
        const colors = getThemeColors();
        const palette = [
            colors.primary,
            '#27AE60',
            colors.accent,
            '#1E96A3',
            '#7C56D1',
            '#B23A28'
        ];

        Object.values(charts).forEach(chart => {
            if (!chart) return;

            const labels = chart.options.plugins?.legend?.labels;
            if (labels) labels.color = colors.textDark;

            if (chart.options.scales) {
                Object.values(chart.options.scales).forEach(scale => {
                    if (scale.ticks) scale.ticks.color = colors.textDark;
                    if (scale.grid?.color) scale.grid.color = colors.borderColor;
                });
            }
        });

        if (charts.trend) {
            charts.trend.data.datasets.forEach((dataset, index) => {
                dataset.borderColor = palette[index % palette.length];
                dataset.backgroundColor = palette[index % palette.length];
            });
        }

        if (charts.program) {
            charts.program.data.datasets[0].backgroundColor =
                charts.program.data.labels.map(
                    (_, index) => palette[index % palette.length]
                );
        }

        ['published-chart', 'utilized-chart', 'presented-chart', 'copyright-chart']
            .forEach(id => {
                const chart = charts[id];
                if (chart) chart.data.datasets[0].backgroundColor[1] = colors.grayLight;
            });

        Object.values(charts).forEach(chart => chart?.update('none'));
    });

});
