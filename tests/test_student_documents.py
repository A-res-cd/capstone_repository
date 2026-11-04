"""Fictional documents and private two-stage import contracts."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from io import BytesIO
from zipfile import ZipFile
from xml.sax.saxutils import escape

from openpyxl import Workbook
import pytest
from werkzeug.datastructures import FileStorage

from app.db import roster, roster_stage
from app.services.student_documents import HEADERS, extract_document
from app.services.roster_import import normalize_candidate
from tests.test_roster_automatic_signup import ROOT, roster_db, isolated_database, feature_app, query, import_list, student

BINDING='fictional-private-session-binding-0123456789'
ROW=['001234','Ada','','Lovelace','ada@example.edu']

def document(kind,rows=None,tables=1):
    rows=rows if rows is not None else [list(HEADERS),ROW]
    output=BytesIO()
    if kind=='xlsx':
        book=Workbook()
        for index in range(tables):
            sheet=book.active if index==0 else book.create_sheet()
            sheet.title='Students '+str(index+1)
            for row in rows:
                sheet.append(row)
        book.save(output)
        book.close()
    elif kind=='docx':
        body=''.join('<w:tbl>'+''.join('<w:tr>'+''.join('<w:tc><w:p><w:r><w:t>'+escape(str(value))+'</w:t></w:r></w:p></w:tc>' for value in row)+'</w:tr>' for row in rows)+'</w:tbl>' for _ in range(tables))
        with ZipFile(output,'w') as archive:
            archive.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'+body+'</w:body></w:document>')
    elif kind=='pdf':
        # Bordered, text-based table; standard PDF objects, no external fixtures.
        stream=[]
        width=110
        for index in range(6):
            x=20+index*width
            stream.append(f'{x} {750-len(rows)*35} m {x} 750 l S')
        for index in range(len(rows)+1):
            y=750-index*35
            stream.append(f'20 {y} m 570 {y} l S')
        for r,row in enumerate(rows):
            for c,value in enumerate(row):
                value=str(value).replace('\\','\\\\').replace('(','\\(').replace(')','\\)')
                stream.append(f'BT /F1 7 Tf {23+c*width} {730-r*35} Td ({value}) Tj ET')
        payload='\n'.join(stream).encode()
        objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',b'<< /Length '+str(len(payload)).encode()+b' >>\nstream\n'+payload+b'\nendstream']
        data=b'%PDF-1.4\n'; offsets=[0]
        for index,obj in enumerate(objects,1):
            offsets.append(len(data)); data+=str(index).encode()+b' 0 obj\n'+obj+b'\nendobj\n'
        xref=len(data)
        data+=b'xref\n0 6\n0000000000 65535 f \n'+b''.join(f'{pos:010d} 00000 n \n'.encode() for pos in offsets[1:])
        data+=f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode()
        output.write(data)
    return output.getvalue()

def stage(kind='xlsx',actor=1,binding=BINDING,update_upload_id=None,**kwargs):
    return roster_stage.create_stage(FileStorage(stream=BytesIO(document(kind,**kwargs)),filename='students.'+kind),'BSIT 1','2026-2027','1',actor,binding,update_upload_id)

@pytest.mark.parametrize('kind',['xlsx','docx','pdf'])
def test_format_mapping_source_and_leading_zero(kind):
    parsed=extract_document(document(kind),'.'+kind)
    assert parsed['format']==kind
    accepted,skipped,display=normalize_candidate(parsed['candidates'][0])
    assert not skipped and accepted[0]['university_no']=='001234'
    assert accepted[0]['email']=='ada@example.edu'
    assert accepted[0]['source']['row']==2
    assert ('worksheet' if kind=='xlsx' else 'page' if kind=='pdf' else 'table') in display[0]['source']

@pytest.mark.parametrize('kind',['xlsx','docx','pdf'])
def test_missing_columns_and_repeated_headers(kind):
    with pytest.raises(ValueError,match='No identifiable'):
        extract_document(document(kind,rows=[['university_num','contact'],['001','a@example.edu']]),'.'+kind)
    parsed=extract_document(document(kind,rows=[list(HEADERS),ROW,list(HEADERS),ROW]),'.'+kind)
    accepted,skipped,_=normalize_candidate(parsed['candidates'][0])
    assert len(accepted)==1 and len(skipped)==2
    assert 'Repeated' in skipped[0]['reason']

@pytest.mark.parametrize('extension',['.xls','.doc'])
def test_legacy_formats_rejected(extension):
    with pytest.raises(ValueError,match='unsupported'):
        extract_document(b'legacy',extension)

def test_scanned_pdf_and_content_mismatch_rejected():
    with pytest.raises(ValueError,match='Scanned/image-only'):
        extract_document(document('pdf',rows=[]),'.pdf')
    with pytest.raises(ValueError):
        extract_document(document('docx'),'.xlsx')

def test_ambiguous_columns_and_numeric_identifiers():
    with pytest.raises(ValueError,match='Ambiguous'):
        extract_document(document('docx',rows=[list(HEADERS),ROW[:-1]]),'.docx')
    parsed=extract_document(document('xlsx',rows=[list(HEADERS),[1234,*ROW[1:]],['1.23E+5',*ROW[1:]]]),'.xlsx')
    accepted,skipped,_=normalize_candidate(parsed['candidates'][0])
    assert not accepted and len(skipped)==2

def test_private_staging_selection_and_idempotence(roster_db):
    token=stage(tables=2)
    preview=roster_stage.preview(token,1,BINDING)
    assert len(preview['candidates'])==2 and 'rows' not in preview
    assert query(roster_db,'SELECT COUNT(*) FROM uploaded_by')==[(0,)]
    with pytest.raises(ValueError,match='Select'):
        roster_stage.confirm(token,1,BINDING)
    with pytest.raises(ValueError,match='Select'):
        roster_stage.confirm(token,1,BINDING,'tampered')
    preview=roster_stage.preview(token,1,BINDING,'1')
    assert preview['summary']['added']==1
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda _:roster_stage.confirm(token,1,BINDING,'1'),range(2)))
    assert results[0]==results[1]
    assert query(roster_db,'SELECT COUNT(*) FROM uploaded_by')==[(1,)]
    assert query(roster_db,'SELECT payload FROM roster_import_stage')==[({'confirmed_result':results[0]},)]

def test_staging_owner_session_expiry_and_cleanup(roster_db):
    token=stage()
    for actor,binding in [(2,BINDING),(1,'other-session-binding-0123456789012345')]:
        with pytest.raises(PermissionError):
            roster_stage.preview(token,actor,binding)
        with pytest.raises(PermissionError):
            roster_stage.confirm(token,actor,binding)
    query(roster_db,"UPDATE roster_import_stage SET expires_at=clock_timestamp()-INTERVAL '1 second'")
    with pytest.raises(roster_stage.StageExpired):
        roster_stage.confirm(token,1,BINDING)
    assert roster_stage.purge_expired()==1
    assert query(roster_db,'SELECT COUNT(*) FROM uploaded_by')==[(0,)]

def test_confirmation_rechecks_claim_and_rolls_back(roster_db,monkeypatch):
    upload=import_list()
    token=stage(update_upload_id=upload,rows=[list(HEADERS),['001234','Changed','','Name','ada@example.edu']])
    assert roster_stage.preview(token,1,BINDING)['summary']['updated']==1
    assert student()[0]
    result=roster_stage.confirm(token,1,BINDING)
    assert result['updated']==0 and result['skipped']==1
    token=stage(update_upload_id=upload,rows=[list(HEADERS),['009999',*ROW[1:]]])
    original=roster.log_audit
    monkeypatch.setattr(roster,'log_audit',lambda *a,**k: (_ for _ in ()).throw(RuntimeError('audit unavailable')))
    with pytest.raises(RuntimeError):
        roster_stage.confirm(token,1,BINDING)
    assert query(roster_db,"SELECT COUNT(*) FROM roster WHERE university_no='009999'")==[(0,)]
    assert query(roster_db,'SELECT upload_id FROM roster_import_stage WHERE stage_id=%s',(token,))==[(None,)]
    monkeypatch.setattr(roster,'log_audit',original)
    assert roster_stage.confirm(token,1,BINDING)['added']==1

def test_masterlist_update_reuses_class_list_and_corrects_rejected_email(roster_db,feature_app):
    upload=import_list([
        ROW,
        ['00002','Grace','','Hopper','grace@example.edu'],
    ])
    before=roster.read_roster(1)[1]
    assert all(row['registration_status']=='Not registered' and row['status']=='active' for row in before)
    client=feature_app.test_client()
    with client.session_transaction() as state:
        state['user_id']=1
    page=client.get(f'/roster?update_upload_id={upload}')
    assert page.status_code==200 and b'name="update_upload_id"' in page.data and b'Update masterlist' in page.data
    duplicate=client.post('/roster',data={'master_list':(BytesIO(document('xlsx')),'students.xlsx'),
        'class_name':'BSIT 1','academic_year':'2026-2027','semester':'1'})
    assert b'already has an active masterlist' in duplicate.data
    ok,result=student(email='correct@example.edu')
    assert ok and result['decision']=='rejected'
    reason=query(roster_db,'SELECT reason FROM signup ORDER BY signup_id DESC LIMIT 1')[0][0]
    assert 'Verified email does not match' in reason
    assert 'Rejected' in next(row for row in roster.read_roster(1)[1] if row['university_no']=='001234')['registration_status']
    with pytest.raises(ValueError,match='already has an active masterlist'):
        stage()
    token=stage(update_upload_id=upload,rows=[list(HEADERS),['001234','Ada','','Lovelace','correct@example.edu']])
    assert roster_stage.preview(token,1,BINDING)['summary']['updated']==1
    update=roster_stage.confirm(token,1,BINDING)
    assert update['upload_id']==upload and update['updated']==1
    assert query(roster_db,'SELECT COUNT(*) FROM uploaded_by')==[(1,)]
    assert query(roster_db,'SELECT COUNT(*) FROM roster')==[(2,)]
    assert student(email='correct@example.edu',resubmit=True)[1]['decision']=='approved'
    assert next(row for row in roster.read_roster(1)[1] if row['university_no']=='001234')['registration_status']=='Verified registered'
    protected=stage(update_upload_id=upload,rows=[list(HEADERS),['001234','Changed','','Name','different@example.edu']])
    assert roster_stage.confirm(protected,1,BINDING)['skipped']==1
    assert roster_stage.confirm(token,1,BINDING)==update
    with pytest.raises(ValueError,match='allowed to update'):
        stage(actor=2,update_upload_id=upload)


def test_duplicate_class_previews_are_rechecked_at_confirmation(roster_db):
    first=stage()
    second=stage()
    roster_stage.confirm(first,1,BINDING)
    with pytest.raises(ValueError,match='already has an active masterlist'):
        roster_stage.confirm(second,1,BINDING)
    assert query(roster_db,'SELECT COUNT(*) FROM uploaded_by')==[(1,)]


def test_confirmation_rechecks_term_and_diagram_columns(roster_db):
    token=stage()
    import_list(year='2027-2028')
    with pytest.raises(ValueError,match='Older-term'):
        roster_stage.confirm(token,1,BINDING)
    columns=query(roster_db,"SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='uploaded_by' ORDER BY ordinal_position")
    assert [r[0] for r in columns]==['upload_id','file_name','class_name','academic_year','semester','status','uploaded_at','file_type','uploader_user_id']
    assert query(roster_db,"SELECT COUNT(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='user' AND column_name='roster_id'")==[(0,)]

@pytest.mark.parametrize('kind',['docx','pdf'])
def test_private_worker_document_import_and_invalid_cleanup(roster_db,kind):
    token=stage(kind)
    assert roster_stage.preview(token,1,BINDING)['summary']['added']==1
    assert roster_stage.confirm(token,1,BINDING)['added']==1
    with pytest.raises(ValueError):
        stage(kind,rows=[['Wrong header'],['Wrong content']])
    assert query(roster_db,'SELECT COUNT(*) FROM roster_import_stage')==[(1,)]
    assert query(roster_db,'SELECT COUNT(*) FROM uploaded_by')==[(1,)]

def test_private_worker_scanned_pdf_actionable(roster_db):
    with pytest.raises(ValueError,match='Scanned/image-only'):
        stage('pdf',rows=[])
    assert query(roster_db,'SELECT COUNT(*) FROM roster_import_stage')==[(0,)]

def test_merged_data_cells_rejected_but_title_allowed():
    output=BytesIO(); book=Workbook(); sheet=book.active
    sheet.append(['Student list']); sheet.merge_cells('A1:E1')
    sheet.append(list(HEADERS)); sheet.append(ROW); book.save(output)
    assert len(extract_document(output.getvalue(),'.xlsx')['candidates'])==1
    sheet.merge_cells('A3:B3'); output=BytesIO(); book.save(output); book.close()
    with pytest.raises(ValueError,match='Merged'):
        extract_document(output.getvalue(),'.xlsx')

def test_separate_worksheet_tables_require_selection():
    parsed=extract_document(document('xlsx',rows=[list(HEADERS),ROW,[],list(HEADERS),['009999',*ROW[1:]]]),'.xlsx')
    assert len(parsed['candidates'])==2
    assert parsed['candidates'][1]['records'][0]['source']['row']==5

def test_stage_http_guards_csrf_and_client_records_ignored(roster_db,feature_app):
    token=stage()
    client=feature_app.test_client()
    for actor in (None,2,3,4):
        with client.session_transaction() as session:
            session.clear()
            if actor:
                session['user_id']=actor
                session['roster_import_binding']=BINDING
        assert client.get('/roster/preview/'+token).status_code==403
        assert client.post('/roster/confirm/'+token).status_code==403
    with client.session_transaction() as session:
        session['user_id']=1; session['roster_import_binding']=BINDING
    feature_app.config['WTF_CSRF_ENABLED']=True
    assert client.post('/roster/confirm/'+token).status_code==400
    feature_app.config['WTF_CSRF_ENABLED']=False
    response=client.post('/roster/confirm/'+token,data={'candidate':'0','added':'999','records':'tampered'})
    assert response.status_code==302
    assert query(roster_db,'SELECT university_no,contact FROM roster')==[('001234','ada@example.edu')]

def test_legacy_pending_student_cannot_bypass_roster(roster_db):
    from app.db import auth,users
    query(roster_db,"UPDATE \"user\" SET account_status='pending' WHERE user_id=3")
    ident=query(roster_db,"INSERT INTO signup(user_id,status,method,requested_at,registration_date) VALUES(3,'pending','manual',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP) RETURNING signup_id")[0][0]
    assert not auth.review_verification_request(ident,'approved','',1)[0]
    assert not users.set_account_status(3,'active',1)[0]
    assert query(roster_db,'SELECT account_status FROM "user" WHERE user_id=3')==[('pending',)]

@pytest.mark.parametrize('schema_file',['capre_revised_schema.sql','capreDB.sql'])
def test_fresh_schema_executes_and_preserves_diagram(roster_db,schema_file):
    with closing(roster_db()) as conn,conn.cursor() as cursor:
        cursor.execute('CREATE SCHEMA fresh_check; SET LOCAL search_path TO fresh_check')
        cursor.execute((ROOT/'database'/schema_file).read_text(encoding='utf-8'))
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='fresh_check' AND table_name='uploaded_by' ORDER BY ordinal_position")
        assert [r[0] for r in cursor.fetchall()]==['upload_id','uploader_user_id','file_name','class_name','academic_year','semester','status','uploaded_at','file_type']
        cursor.execute("SELECT relrowsecurity FROM pg_class WHERE oid='roster_import_stage'::regclass")
        assert cursor.fetchone()==(True,)
        cursor.execute("SELECT relrowsecurity FROM pg_class WHERE oid IN ('roster'::regclass,'uploaded_by'::regclass)")
        assert cursor.fetchall()==[(True,),(True,)]
        # Rollback removes this entire fresh-install rehearsal.
