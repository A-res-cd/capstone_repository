document.addEventListener('DOMContentLoaded', () => {
    const modal = document.getElementById('analytics-export-modal');
    const form = document.getElementById('analytics-export-form');
    const context = document.getElementById('analytics-export-context');
    const closeButton = document.getElementById('analytics-export-close');
    const cancelButton = document.getElementById('analytics-export-cancel');
    const submitButton = document.getElementById('analytics-export-submit');
    const excelOption = document.getElementById('analytics-export-excel');
    const table = document.querySelector('.analytics-table');

    if (!modal || !form || !table) return;

    let activeTrigger = null;
    const formatInputs = [...form.querySelectorAll('input[name="export-format"]')];

    const updateExportState = () => {
        submitButton.disabled = !formatInputs.some(input => input.checked);
    };

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
    const yesNo = value => value ? 'Yes' : 'No';
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

    const closeModal = () => {
        modal.hidden = true;
        document.body.classList.remove('analytics-export-modal-open');
        activeTrigger?.focus();
    };

    const openModal = trigger => {
        activeTrigger = trigger;
        const row = trigger.closest('[data-report-row]');
        const scope = trigger.dataset.reportScope;
        const name = scope === 'dashboard'
            ? 'the complete analytics dashboard'
            : scope === 'all'
                ? 'all specialization capstone records'
                : `${readRow(row).Specialization} specialization`;

        const hasWorkbook = Boolean(trigger.dataset.workbookUrl);
        excelOption.hidden = !hasWorkbook;
        formatInputs.forEach(input => { input.checked = false; });
        updateExportState();
        context.textContent = `Choose a file type for ${name}.`;
        modal.hidden = false;
        document.body.classList.add('analytics-export-modal-open');
        formatInputs.find(input => !input.closest('[hidden]'))?.focus();
    };

    const safeFilename = value => value
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-|-$/g, '') || 'analytics';

    const download = (content, type, filename) => {
        const blob = content instanceof Blob ? content : new Blob([content], { type });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    };

    const exportWorkbook = async () => {
        const response = await fetch(activeTrigger.dataset.workbookUrl);
        if (!response.ok) {
            let message = 'Unable to create the Excel workbook.';
            try {
                const payload = await response.json();
                message = payload.error || message;
            } catch (_) {
                // Keep the readable fallback for non-JSON server errors.
            }
            throw new Error(message);
        }

        download(
            await response.blob(),
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            response.headers.get('Content-Disposition')?.match(/filename="?([^";]+)"?/)?.[1]
                || 'capre-specializations.xlsx'
        );
    };

    const exportCsv = report => {
        const escapeCell = value => `"${String(value).replace(/"/g, '""')}"`;
        const rows = [
            [`CAPRE Analytics Report - ${report.name}`],
            [`Generated: ${new Date().toLocaleString()}`]
        ];

        report.sections.forEach(section => {
            rows.push([], [section.title], section.columns, ...section.rows);
        });

        const csv = rows.map(row => row.map(escapeCell).join(',')).join('\r\n');

        download(
            `\uFEFF${csv}`,
            'text/csv;charset=utf-8',
            `analytics-${safeFilename(report.name)}.csv`
        );
    };

    const pdfSafe = value => String(value)
        .normalize('NFKD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/[^\x20-\x7E]/g, '?')
        .replace(/([\\()])/g, '\\$1');

    const wrapPdfLine = (line, maxLength = 88) => {
        if (line.length <= maxLength) return [line];

        const indent = line.match(/^\s*/)[0];
        const wrapped = [];
        let remaining = line.trim();
        while (remaining.length > maxLength - indent.length) {
            let splitAt = remaining.lastIndexOf(' ', maxLength - indent.length);
            if (splitAt < 1) splitAt = maxLength - indent.length;
            wrapped.push(`${indent}${remaining.slice(0, splitAt)}`);
            remaining = remaining.slice(splitAt).trim();
        }
        wrapped.push(`${indent}${remaining}`);
        return wrapped;
    };

    const createPdf = report => {
        const lines = [
            `CAPRE Analytics Report - ${report.name}`,
            `Generated: ${new Date().toLocaleString()}`,
            ''
        ];

        report.sections.forEach(section => {
            lines.push(section.title.toUpperCase(), '');
            if (!section.rows.length) lines.push('No capstone records found.', '');
            section.rows.forEach(row => {
                section.columns.forEach((column, index) => {
                    lines.push(`${index ? '  ' : ''}${column}: ${row[index]}`);
                });
                lines.push('');
            });
        });

        const wrappedLines = lines.flatMap(line => wrapPdfLine(line));
        const linePages = [];
        for (let index = 0; index < wrappedLines.length; index += 50) {
            linePages.push(wrappedLines.slice(index, index + 50));
        }

        const objects = [];
        const pageReferences = linePages.map((_, index) => `${4 + (index * 2)} 0 R`);
        objects[1] = '<< /Type /Catalog /Pages 2 0 R >>';
        objects[2] = `<< /Type /Pages /Kids [${pageReferences.join(' ')}] /Count ${linePages.length} >>`;
        objects[3] = '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>';

        linePages.forEach((pageLines, index) => {
            const pageId = 4 + (index * 2);
            const contentId = pageId + 1;
            const stream = [
                'BT',
                '/F1 10 Tf',
                '36 756 Td',
                '14 TL',
                ...pageLines.map(line => `(${pdfSafe(line)}) Tj\nT*`),
                'ET'
            ].join('\n');

            objects[pageId] = `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents ${contentId} 0 R >>`;
            objects[contentId] = `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`;
        });

        let pdf = '%PDF-1.4\n';
        const offsets = [0];
        for (let index = 1; index < objects.length; index += 1) {
            offsets[index] = pdf.length;
            pdf += `${index} 0 obj\n${objects[index]}\nendobj\n`;
        }

        const xrefOffset = pdf.length;
        pdf += `xref\n0 ${objects.length}\n0000000000 65535 f \n`;
        for (let index = 1; index < objects.length; index += 1) {
            pdf += `${String(offsets[index]).padStart(10, '0')} 00000 n \n`;
        }
        pdf += `trailer\n<< /Size ${objects.length} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF`;

        download(
            pdf,
            'application/pdf',
            `analytics-${safeFilename(report.name)}.pdf`
        );
    };

    document.querySelectorAll('[data-export-report]').forEach(trigger => {
        trigger.addEventListener('click', () => openModal(trigger));
    });

    document.querySelectorAll('.analytics-export-format').forEach(option => {
        const input = option.querySelector('input[name="export-format"]');
        input.addEventListener('change', updateExportState);
        input.addEventListener('keydown', event => {
            if (event.key !== ' ' && event.key !== 'Enter') return;
            event.preventDefault();
            input.checked = !input.checked;
            updateExportState();
        });
        option.addEventListener('click', event => {
            if (event.target === input) {
                updateExportState();
                return;
            }
            event.preventDefault();
            input.checked = !input.checked;
            input.focus();
            updateExportState();
        });
    });

    closeButton?.addEventListener('click', closeModal);
    cancelButton?.addEventListener('click', closeModal);
    modal.addEventListener('click', event => {
        if (event.target === modal) closeModal();
    });
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && !modal.hidden) closeModal();
    });

    form.addEventListener('submit', async event => {
        event.preventDefault();
        const format = new FormData(form).get('export-format');
        if (!format) return;
        submitButton.disabled = true;

        try {
            if (format === 'xlsx') {
                await exportWorkbook();
            } else {
                const report = await getReport();
                if (format === 'pdf') createPdf(report);
                else exportCsv(report);
            }

            closeModal();
        } catch (error) {
            context.textContent = error.message;
        } finally {
            updateExportState();
        }
    });
});
