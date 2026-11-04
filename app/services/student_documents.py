"""Pure document adapters, also loaded by the isolated document worker (no Flask/DB)."""
import csv
from io import BytesIO, StringIO
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile, BadZipFile

MAX_ROWS = 10000
MAX_COLUMNS = 40
MAX_TABLES = 64
HEADERS = ('university_num','user_first_name','user_middle_name','user_last_name','contact')
ALIASES = {
    'university_no': {'university_num','university_no','university_number','student_no','student_number'},
    'first_name': {'user_first_name','first_name'},
    'middle_name': {'user_middle_name','middle_name'},
    'last_name': {'user_last_name','last_name'},
    'email': {'contact','email','email_address'},
}
REQUIRED = {'university_no','first_name','last_name','email'}

def header_mapping(values):
    result = {}
    duplicates=set()
    for index,value in enumerate(values):
        header = re.sub(r'[\s_.-]+','_',str(value or '').strip().lower()).strip('_')
        for field,aliases in ALIASES.items():
            if header in aliases:
                if field in result:
                    duplicates.add(field)
                result[field] = index
    if duplicates and REQUIRED<=result.keys():
        raise ValueError('Ambiguous duplicate header aliases.')
    return result

def candidate(label, rows, sources, text_ids=None, ambiguous=False):
    """One rectangular table; repeated identical headers are explicit skipped rows."""
    first = None
    mapping = None
    for index,values in enumerate(rows):
        found = header_mapping(values)
        if REQUIRED <= found.keys():
            first,mapping = index,found
            break
    if first is None:
        raise ValueError('No required student headers (university_num, user_first_name, user_last_name, contact).')
    if (any(ambiguous[first:]) if isinstance(ambiguous,list) else ambiguous):
        raise ValueError('Merged or nested table cells are ambiguous; use a rectangular table.')
    width = len(rows[first])
    if width>MAX_COLUMNS or any(len(values)!=width for values in rows[first:]):
        raise ValueError('Ambiguous column alignment; every table row must have the same columns.')
    records = []
    for index,values in enumerate(rows[first+1:],first+1):
        found = header_mapping(values)
        repeated = REQUIRED <= found.keys()
        if repeated and found!=mapping:
            raise ValueError('Repeated headers change column order; split into separate tables.')
        record = {field:str(values[column] if values[column] is not None else '').strip() for field,column in mapping.items()}
        record.update(source=sources[index],identifier_is_text=(text_ids[index][mapping['university_no']] if text_ids else True),repeated_header=repeated)
        records.append(record)
    return {'label':label,'columns':{field:str(rows[first][column]) for field,column in mapping.items()},'records':records}

def _zip(content, marker):
    zipped = ZipFile(BytesIO(content))
    names = set(zipped.namelist())
    if marker not in names or len(names)>2000 or sum(i.file_size for i in zipped.infolist())>30*1024**2:
        zipped.close()
        raise ValueError('Document content does not match its format or exceeds the expanded-file budget.')
    if marker=='xl/workbook.xml' and 'word/document.xml' in names or marker=='word/document.xml' and 'xl/workbook.xml' in names:
        zipped.close()
        raise ValueError('Ambiguous document format.')
    return zipped

def xlsx_tables(content):
    from openpyxl import load_workbook
    with _zip(content,'xl/workbook.xml'):
        pass
    book = load_workbook(BytesIO(content),read_only=False,data_only=False,keep_links=False)
    try:
        if len(book.worksheets)>MAX_TABLES:
            raise ValueError('Too many worksheets.')
        for sheet in book.worksheets:
            if sheet.max_row is None or sheet.max_column is None or sheet.max_row>MAX_ROWS+1 or sheet.max_column>MAX_COLUMNS:
                raise ValueError('Verify worksheet dimensions: at most 10000 rows and 40 columns.')
            rows,flags,sources = [],[],[]
            for row in sheet.iter_rows():
                rows.append([str(cell.value) if cell.value is not None else '' for cell in row])
                flags.append([isinstance(cell.value,str) and cell.data_type!='f' for cell in row])
                sources.append({'worksheet':sheet.title,'row':len(rows)})
            merges=[False]*len(rows)
            for merged in sheet.merged_cells.ranges:
                for index in range(merged.min_row-1,min(merged.max_row,len(rows))):
                    merges[index]=True
            # Blank separators define independent worksheet tables. Repeated
            # headers without a separator remain explicit skipped rows.
            start=0
            blocks=[]
            for index in range(len(rows)+1):
                if index==len(rows) or not any(str(value).strip() for value in rows[index]):
                    if index>start:
                        blocks.append((start,index))
                    start=index+1
            for number,(start,end) in enumerate(blocks,1):
                label=sheet.title if len(blocks)==1 else f'{sheet.title}, table {number}'
                yield label,rows[start:end],sources[start:end],flags[start:end],merges[start:end]
    finally:
        book.close()

def docx_tables(content):
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    with _zip(content,'word/document.xml') as zipped:
        root=ET.fromstring(zipped.read('word/document.xml'))
    tables=root.findall('.//w:body/w:tbl',ns)
    if len(tables)>MAX_TABLES:
        raise ValueError('Too many Word tables.')
    for number,table in enumerate(tables,1):
        rows,ambiguous=[],[]
        for row in table.findall('w:tr',ns):
            ambiguous.append(bool(row.findall('.//w:gridSpan',ns) or row.findall('.//w:vMerge',ns) or row.findall('.//w:tbl',ns)))
            values=[]
            for cell in row.findall('w:tc',ns):
                values.append('\n'.join(''.join(t.text or '' for t in paragraph.findall('.//w:t',ns)) for paragraph in cell.findall('w:p',ns)))
            rows.append(values)
            if len(rows)>MAX_ROWS+1 or len(values)>MAX_COLUMNS:
                raise ValueError('Word table exceeds row/column limits.')
        yield f'Table {number}',rows,[{'table':number,'row':r} for r in range(1,len(rows)+1)],None,ambiguous

def pdf_tables(content):
    import pdfplumber
    if not content.startswith(b'%PDF-'):
        raise ValueError('PDF extension does not match the document contents.')
    with pdfplumber.open(BytesIO(content)) as pdf:
        if pdf.doc.encryption or len(pdf.pages)>50:
            raise ValueError('Use an unencrypted PDF of at most 50 pages.')
        text_found=False
        count=0
        for page_number,page in enumerate(pdf.pages,1):
            text_found=bool(page.extract_text()) or text_found
            tables=page.find_tables()
            if not tables and page.extract_text():
                tables=page.find_tables({'vertical_strategy':'text','horizontal_strategy':'text','min_words_vertical':2})
            for table_number,table in enumerate(tables,1):
                rows=table.extract()
                ambiguous=[any(cell is None for cell in row.cells) for row in table.rows]
                count+=1
                if count>MAX_TABLES:
                    raise ValueError('Too many PDF tables.')
                yield f'Page {page_number}, table {table_number}',rows,[{'page':page_number,'table':table_number,'row':r} for r in range(1,len(rows)+1)],None,ambiguous
        if not text_found:
            raise ValueError('Scanned/image-only PDF is unsupported. Export a text-based PDF table or upload XLSX/DOCX; roster OCR is not used.')

def extract_document(content,extension):
    if not content or len(content)>5*1024**2:
        raise ValueError('Choose a nonempty document up to 5 MiB.')
    try:
        if extension=='.xlsx':
            tables=xlsx_tables(content)
        elif extension=='.docx':
            tables=docx_tables(content)
        elif extension=='.pdf':
            tables=pdf_tables(content)
        elif extension=='.csv':
            rows=[]
            for row in csv.reader(StringIO(content.decode('utf-8-sig')),strict=True):
                if len(rows)>MAX_ROWS or len(row)>MAX_COLUMNS:
                    raise ValueError('CSV exceeds row/column limits.')
                rows.append(row)
            width=max(map(len,rows),default=0)
            # CSV omitted trailing cells are blank values, not shifted columns.
            rows=[row+['']*(width-len(row)) for row in rows]
            tables=[('CSV table',rows,[{'table':1,'row':r} for r in range(1,len(rows)+1)],None,False)]
        else:
            raise ValueError('Use XLSX, DOCX, text-based PDF or CSV. Legacy XLS/DOC are unsupported.')
        candidates,warnings,total=[],[],0
        for label,rows,sources,flags,ambiguous in tables:
            total+=len(rows)
            if total>MAX_ROWS+MAX_TABLES:
                raise ValueError('Document exceeds 10000 extracted rows.')
            try:
                found=candidate(label,rows,sources,flags,ambiguous)
            except ValueError as exc:
                warnings.append(label+': '+str(exc))
            else:
                found['id']=str(len(candidates))
                candidates.append(found)
        if not candidates:
            raise ValueError('No identifiable valid student table. '+('; '.join(warnings[:3]) or 'Use the provided headers in a rectangular table.'))
        return {'format':extension.lstrip('.'),'candidates':candidates,'warnings':warnings}
    except (BadZipFile,ET.ParseError,KeyError,UnicodeError,csv.Error,OSError) as exc:
        raise ValueError('Document could not be parsed; export a supported table using the template.') from exc
