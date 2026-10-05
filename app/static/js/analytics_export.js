document.addEventListener('DOMContentLoaded', () => {
    const table = document.querySelector('.analytics-table');
    if (!table) return;
    let activeTrigger = null;
    const readRow = row => Object.fromEntries(
        [...row.querySelectorAll('[data-report-field]')].map(cell => [
            cell.dataset.reportField,
            cell.textContent.trim().replace(/\s+/g, ' ')
        ])
    );

    const recordColumns = [
        'ID',
        'Capstone Title',
        'Authors',
        'Adviser',
        'Year',
        'Specialization',
        'Published',
        'Utilized',
        'Presented',
        'Copyright Registered'
    ];
    const yesNo = value => value == null ? 'Not reviewed' : value ? 'Yes' : 'No';
    const formatRecord = (record, specialization) => [
        record.id,
        record.capstone_title || '',
        record.authors || 'Not recorded',
        record.adviser || 'Not recorded',
        record.year || '',
        record.specialization || specialization,
        yesNo(record.published),
        yesNo(record.utilized),
        yesNo(record.presented),
        yesNo(record.copyright_registered)
    ];

    const getSummaryReport = () => {
        const allRows = [...table.querySelectorAll('[data-report-row]')];
        const isFullReport = activeTrigger?.dataset.reportScope === 'all';
        const rows = isFullReport
            ? allRows.map(readRow)
            : [readRow(activeTrigger.closest('[data-report-row]'))];
        const name = isFullReport ? 'All Specializations' : rows[0].Specialization;

        return {
            name,
            sections: [{
                title: 'Summary by Specialization',
                columns: Object.keys(rows[0]),
                rows: rows.map(row => Object.values(row))
            }]
        };
    };

    const getSpecializationReport = async () => {
        const response = await fetch(activeTrigger.dataset.reportUrl, {
            headers: { 'Accept': 'application/json' }
        });
        const payload = await response.json();

        if (!response.ok || !payload.success) {
            throw new Error(payload.error || 'Unable to load the specialization report.');
        }

        return {
            name: payload.specialization,
            sections: [{
                title: `${payload.specialization} Capstone Records`,
                columns: recordColumns,
                rows: payload.records.map(record => formatRecord(record, payload.specialization))
            }]
        };
    };

    const getAllSpecializationsReport = async () => {
        const response = await fetch(activeTrigger.dataset.reportUrl, {
            headers: { 'Accept': 'application/json' }
        });
        const payload = await response.json();

        if (!response.ok || !payload.success) {
            throw new Error(payload.error || 'Unable to load all specialization reports.');
        }

        return {
            name: 'All Specializations',
            sections: payload.specializations.map(specialization => ({
                title: `${specialization.specialization_name} Capstone Records`,
                columns: recordColumns,
                rows: specialization.records.map(record =>
                    formatRecord(record, specialization.specialization_name)
                )
            }))
        };
    };

    const getDashboardReport = () => {
        const data = window.chartData || {};
        const programLabels = data.program_labels || [];
        const programTotals = data.program_totals || [];
        const specializationLabels = data.specialization_labels || [];
        const specializationTotals = data.specialization_totals || [];
        const trendYears = data.trend_years || [];
        const trendSeries = data.trend_series || {};
        const total = programTotals.reduce((sum, value) => sum + Number(value || 0), 0);
        const share = value => `${total ? ((Number(value) / total) * 100).toFixed(1) : '0.0'}%`;
        const summaryRows = [...table.querySelectorAll('[data-report-row]')].map(readRow);
        const statusGroups = [
            ['Publication', data.published_labels || [], data.published_totals || []],
            ['Utilization', data.utilized_labels || [], data.utilized_totals || []],
            ['Presentation', data.presented_labels || [], data.presented_totals || []],
            ['Copyright', data.copyright_labels || [], data.copyright_totals || []]
        ];
        const statusRows = statusGroups.flatMap(([metric, labels, values]) => {
            const groupTotal = values.reduce((sum, value) => sum + Number(value || 0), 0);
            return labels.map((label, index) => {
                const value = Number(values[index] || 0);
                const percentage = groupTotal ? ((value / groupTotal) * 100).toFixed(1) : '0.0';
                return [metric, label, value, `${percentage}%`];
            });
        });
        const trendSpecializations = Object.keys(trendSeries);

        return {
            name: 'Full Analytics',
            sections: [
                {
                    title: 'Abbreviation Legend',
                    columns: ['Code', 'Full Name'],
                    rows: (data.abbreviations || []).map(item => [item.code, item.name])
                },
                {
                    title: 'Overview',
                    columns: ['Metric', 'Value'],
                    rows: [['Total Capstones', total]]
                },
                {
                    title: 'Capstones by Program',
                    columns: ['Program', 'Capstones', 'Share of Total'],
                    rows: programLabels.map((label, index) => [
                        label,
                        Number(programTotals[index] || 0),
                        share(programTotals[index] || 0)
                    ])
                },
                {
                    title: 'Capstone Status',
                    columns: ['Metric', 'Status', 'Count', 'Share'],
                    rows: statusRows
                },
                {
                    title: 'Capstone Trend per Year',
                    columns: ['Year', ...trendSpecializations],
                    rows: trendYears.map((year, index) => [
                        year,
                        ...trendSpecializations.map(name => Number(trendSeries[name][index] || 0))
                    ])
                },
                {
                    title: 'Capstones by Specialization',
                    columns: ['Specialization', 'Capstones', 'Share of Total'],
                    rows: specializationLabels.map((label, index) => [
                        label,
                        Number(specializationTotals[index] || 0),
                        share(specializationTotals[index] || 0)
                    ])
                },
                {
                    title: 'Summary by Specialization',
                    columns: Object.keys(summaryRows[0] || {}),
                    rows: summaryRows.map(row => Object.values(row))
                }
            ].filter(section => section.columns.length && section.rows.length)
        };
    };

    const getReport = () => {
        if (activeTrigger?.dataset.reportScope === 'dashboard') {
            return getDashboardReport();
        }

        if (activeTrigger?.dataset.reportScope === 'row') {
            return getSpecializationReport();
        }

        if (activeTrigger?.dataset.reportScope === 'all') {
            return getAllSpecializationsReport();
        }

        return getSummaryReport();
    };

    document.querySelectorAll('[data-print-report]').forEach(trigger => {
        trigger.addEventListener('click', async () => {
            const printWindow = window.open('', '_blank');
            if (!printWindow) {
                alert('Allow pop-ups to open the print view.');
                return;
            }
            printWindow.opener = null;
            activeTrigger = trigger;
            const doc = printWindow.document;
            doc.title = 'CAPRE Report';
            const status = doc.createElement('p');
            status.textContent = 'Preparing report...';
            doc.body.appendChild(status);
            try {
                const report = await getReport();
                if (printWindow.closed) return;
                status.remove();
                const style = doc.createElement('style');
                style.textContent = '@page {size: landscape; margin: 12mm} body {font: 12px Arial; color:#111} table {width:100%; border-collapse:collapse; margin-bottom:24px} th,td {border:1px solid #aaa; padding:6px; text-align:left; overflow-wrap:anywhere} thead {display:table-header-group} tr {break-inside:avoid} h2 {break-after:avoid} @media print {.print-controls{display:none}}';
                doc.head.appendChild(style);
                const heading = doc.createElement('h1');
                heading.textContent = 'CAPRE - ' + report.name;
                doc.body.appendChild(heading);
                const info = doc.createElement('p');
                info.textContent = 'Year: ' + (new URLSearchParams(location.search).get('year') || 'All years') + ' | Generated: ' + new Date().toLocaleString();
                doc.body.appendChild(info);
                const button = doc.createElement('button');
                button.className = 'print-controls';
                button.textContent = 'Print report';
                button.addEventListener('click', () => printWindow.print());
                doc.body.appendChild(button);
                report.sections.forEach(section => {
                    const title = doc.createElement('h2');
                    title.textContent = section.title;
                    doc.body.appendChild(title);
                    const table = doc.createElement('table');
                    const header = table.createTHead().insertRow();
                    section.columns.forEach(value => {
                        const th = doc.createElement('th');
                        th.textContent = value;
                        header.appendChild(th);
                    });
                    const body = table.createTBody();
                    section.rows.forEach(values => {
                        const row = body.insertRow();
                        values.forEach(value => { row.insertCell().textContent = String(value ?? ''); });
                    });
                    doc.body.appendChild(table);
                });
                printWindow.focus();
                printWindow.requestAnimationFrame(() => printWindow.print());
            } catch (error) {
                status.textContent = 'Could not prepare report. Please close this tab and try again.';
            }
        });
    });
});
