"""Small XLSX writer for specialization reports using Python's standard library."""
from html import escape
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile


REPORT_COLUMNS = (
    ("id", "ID"),
    ("capstone_title", "Capstone Title"),
    ("authors", "Authors"),
    ("adviser", "Adviser"),
    ("year", "Year"),
    ("specialization", "Specialization"),
    ("published", "Published"),
    ("utilized", "Utilized"),
    ("presented", "Presented"),
    ("copyright_registered", "Copyright Registered"),
)

_COLUMN_WIDTHS = (9, 48, 45, 30, 11, 20, 13, 13, 13, 24)
_INVALID_SHEET_CHARS = set("[]:*?/\\")


def _sheet_title(value, used_titles):
    base = "".join("_" if char in _INVALID_SHEET_CHARS else char for char in str(value))
    base = base.strip(" '")[:31] or "Specialization"
    title = base
    suffix = 2
    while title.lower() in used_titles:
        marker = f" ({suffix})"
        title = f"{base[:31 - len(marker)]}{marker}"
        suffix += 1
    used_titles.add(title.lower())
    return title


def _cell_value(value, key):
    if key in {"published", "utilized", "presented", "copyright_registered"}:
        return "Yes" if value else "No"
    if key in {"authors", "adviser"} and not value:
        return "Not recorded"
    return "" if value is None else value


def _xml_text(value):
    text = "".join(
        char for char in str(value)
        if ord(char) >= 32 or char in "\t\n\r"
    )
    return escape(text, quote=False)


def _column_name(index):
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _cell(reference, value, style):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{reference}" s="{style}"><v>{value}</v></c>'
    return (
        f'<c r="{reference}" t="inlineStr" s="{style}">'
        f'<is><t>{_xml_text(value)}</t></is></c>'
    )


def _worksheet_xml(headers, data_rows, widths):
    header_cells = "".join(
        _cell(f"{_column_name(index)}1", label, 1)
        for index, label in enumerate(headers, 1)
    )
    rows = [f'<row r="1" ht="28" customHeight="1">{header_cells}</row>']

    for row_number, values in enumerate(data_rows, 2):
        cells = "".join(
            _cell(f"{_column_name(column_number)}{row_number}", value, 2)
            for column_number, value in enumerate(values, 1)
        )
        rows.append(f'<row r="{row_number}">{cells}</row>')

    columns = "".join(
        f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        for index, width in enumerate(widths, 1)
    )
    last_row = max(1, len(data_rows) + 1)
    last_column = _column_name(len(headers))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '</sheetView></sheetViews>'
        '<sheetFormatPr defaultRowHeight="18"/>'
        f'<cols>{columns}</cols><sheetData>{"".join(rows)}</sheetData>'
        f'<autoFilter ref="A1:{last_column}{last_row}"/>'
        '</worksheet>'
    )


def build_table_workbook(tables):
    """Build a styled XLSX workbook from tabular worksheet definitions."""
    used_titles = set()
    sheets = [
        (
            _sheet_title(table["title"], used_titles),
            table["headers"],
            table.get("rows", []),
            table.get("widths") or tuple(18 for _ in table["headers"]),
        )
        for table in tables
    ]
    if not sheets:
        sheets = [("Report", ("Message",), [("No data available",)], (30,))]

    content_types = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
    ]
    content_types.extend(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, len(sheets) + 1)
    )
    content_types.append('</Types>')

    workbook_sheets = "".join(
        f'<sheet name="{escape(title, quote=True)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, (title, _, _, _) in enumerate(sheets, 1)
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets>{workbook_sheets}</sheets></workbook>'
    )

    relationships = "".join(
        f'<Relationship Id="rId{index}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, len(sheets) + 1)
    )
    relationships += (
        f'<Relationship Id="rId{len(sheets) + 1}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'{relationships}</Relationships>'
    )

    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        '</Relationships>'
    )
    styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="3"><fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FF2E3F92"/><bgColor indexed="64"/></patternFill></fill></fills>'
        '<borders count="2"><border/><border><left style="thin"><color rgb="FFD9DCEB"/></left>'
        '<right style="thin"><color rgb="FFD9DCEB"/></right><top style="thin"><color rgb="FFD9DCEB"/></top>'
        '<bottom style="thin"><color rgb="FFD9DCEB"/></bottom></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '</styleSheet>'
    )

    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as workbook:
        workbook.writestr("[Content_Types].xml", "".join(content_types))
        workbook.writestr("_rels/.rels", root_rels)
        workbook.writestr("xl/workbook.xml", workbook_xml)
        workbook.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        workbook.writestr("xl/styles.xml", styles)
        for index, (_, headers, rows, widths) in enumerate(sheets, 1):
            workbook.writestr(
                f"xl/worksheets/sheet{index}.xml",
                _worksheet_xml(headers, rows, widths),
            )

    output.seek(0)
    return output


def build_specialization_workbook(specializations):
    """Build a real XLSX workbook with one worksheet per specialization."""
    return build_table_workbook([
        {
            "title": item["specialization_name"],
            "headers": tuple(label for _, label in REPORT_COLUMNS),
            "rows": [
                tuple(_cell_value(record.get(key), key) for key, _ in REPORT_COLUMNS)
                for record in item.get("records", [])
            ],
            "widths": _COLUMN_WIDTHS,
        }
        for item in specializations
    ])
