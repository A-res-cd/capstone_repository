"""Real PostgreSQL invariants for roster imports and automatic student eligibility."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import csv
import shutil
from io import BytesIO, StringIO
from pathlib import Path
from threading import Event
from uuid import uuid4

from flask_mail import Mail
from openpyxl import Workbook
import psycopg2
from psycopg2 import sql
import pytest
from werkzeug.datastructures import FileStorage

from app.db import auth, migration_runner, roster, roster_stage, signup_delivery, signup_verification, users
from app.utils import document_processing
from app.services.roster_import import parse_upload
from tests.test_original_branch_features import isolated_database, feature_app

ROOT = Path(__file__).resolve().parents[1]
NEW = '20261106_roster_auto_signup.sql'

@pytest.fixture
def roster_db(isolated_database,monkeypatch,request,tmp_path):
    name = 'roster_' + uuid4().hex
    with closing(psycopg2.connect(**isolated_database)) as conn:
        conn.autocommit = True
        with conn.cursor() as cursor:
            cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    def connect():
        return psycopg2.connect(**{**isolated_database,'dbname':name})
    for module in (auth,migration_runner,roster,roster_stage,signup_delivery,signup_verification,users,document_processing):
        monkeypatch.setattr(module,'db_connect',connect)
    try:
        with closing(connect()) as conn,conn.cursor() as cursor:
            cursor.execute((ROOT/'database/capre_original_final.sql').read_text(encoding='utf-8'))
            conn.commit()
        if getattr(request,'param',None)=='historical':
            historical=tmp_path/'historical'
            historical.mkdir()
            for path in migration_runner.migration_files():
                if path.name<NEW:
                    shutil.copyfile(path,historical/path.name)
            migration_runner.upgrade_database(historical)
        else:
            migration_runner.upgrade_database()
        with closing(connect()) as conn,conn.cursor() as cursor:
            cursor.execute("INSERT INTO role(role_id,role_name) VALUES(17,'Student'),(23,'Faculty'),(31,'Admin'),(47,'Capstone Professor')")
            cursor.execute('''INSERT INTO "user"(role_id,account_status,user_first_name)
                VALUES(31,'active','Admin'),(47,'active','Professor'),(17,'active','Student'),(23,'active','Faculty')''')
            conn.commit()
        yield connect
    finally:
        with closing(psycopg2.connect(**isolated_database)) as conn:
            conn.autocommit = True
            with conn.cursor() as cursor:
                cursor.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))

def file(rows=None,headers=None):
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(headers or ['university_no','first_name','middle_name','last_name','email'])
    writer.writerows(rows if rows is not None else [['001234','Ada','','Lovelace','ada@example.edu']])
    return FileStorage(stream=BytesIO(output.getvalue().encode()),filename='students.csv')

def import_list(rows=None,year='2026-2027',semester='1',actor=1):
    return roster.import_roster(file(rows),'BSIT 1',year,semester,actor)['upload_id']

def proof(email):
    ident,code = signup_verification.create_email_code(email)
    assert signup_verification.verify_email_code(ident,email,code)
    return ident

def student(email='ada@example.edu',number='001234',username='ada',**kwargs):
    return auth.create_user('Different','','Name',number,email,username,'Secure123',
        cor_filename='registration.pdf',requested_role='Student',
        signup_verification_id=kwargs.pop('signup_verification_id',None) or proof(email),**kwargs)

def query(connect,statement,params=()):
    with closing(connect()) as conn,conn.cursor() as cursor:
        cursor.execute(statement,params)
        rows = cursor.fetchall() if cursor.description else None
        conn.commit()
        return rows

def test_csv_aliases_normalization_duplicates_and_invalid_rows():
    accepted,skipped = parse_upload(file([
        [' 001234 ',' Ada ','',' Lovelace ',' ADA@EXAMPLE.EDU '],
        ['001234','Second','','Name','other@example.edu'],
        ['','','','',''],['00002','A','','B','bad'],['00003','','','B','a@example.edu']],
        ['Student Number','First Name','Middle Name','Last Name','Email Address']))
    assert accepted[0]['university_no']=='001234' and accepted[0]['email']=='ada@example.edu'
    assert len(accepted)==1 and [r['row'] for r in skipped]==[3,4,5,6]

@pytest.mark.parametrize('headers',[['university_no','email'],['university_no','student_no','first_name','last_name','email']])
def test_missing_or_ambiguous_headers_reject_entire_file(headers):
    with pytest.raises(ValueError):
        parse_upload(file([],headers))

def test_xlsx_numeric_scientific_and_formula_ids_not_coerced():
    book=Workbook(); sheet=book.active
    sheet.append(['university_no','first_name','last_name','email'])
    for number in ('001234',1234,'1E05','=1234'):
        sheet.append([number,'Ada','Lovelace','ada@example.edu'])
    output=BytesIO(); book.save(output); book.close()
    accepted,skipped=parse_upload(FileStorage(stream=BytesIO(output.getvalue()),filename='students.xlsx'))
    assert [r['university_no'] for r in accepted]==['001234'] and len(skipped)==3

def test_import_counts_updates_association_and_persisted_result(roster_db):
    result=roster.import_roster(file(),'BSIT 1','2026-2027','1',1)
    assert (result['added'],result['updated'],result['skipped'],result['skipped_rows'])==(1,0,0,[])
    first=result['upload_id']
    original=query(roster_db,'SELECT roster_id,upload_id FROM roster')[0]
    second=import_list([['001234','Augusta','','Lovelace','ada@example.edu'],['001235','Grace','','Hopper','grace@example.edu'],['001235','Duplicate','','Person','other@example.edu']])
    assert query(roster_db,"SELECT (a.new_values::jsonb->>'added')::int,(a.new_values::jsonb->>'updated')::int,(a.new_values::jsonb->>'skipped')::int,u.status FROM uploaded_by u JOIN audit a ON a.affected_table='uploaded_by' AND a.action_type='roster_upload' AND a.affected_record_id=u.upload_id WHERE u.upload_id=%s",(second,))==[(1,1,1,'active')]
    assert query(roster_db,'SELECT roster_id,upload_id FROM roster WHERE university_no=%s',('001234',))[0]==original
    assert query(roster_db,"SELECT COUNT(*) FROM audit WHERE action_type='roster_correction'")==[(1,)]
    assert query(roster_db,"SELECT new_values::jsonb FROM audit WHERE action_type='roster_upload' AND affected_table='uploaded_by' AND affected_record_id=%s",(second,))[0][0]['skipped_rows'][0]['row']==4
    identical=import_list([['001234','Augusta','','Lovelace','ada@example.edu']])
    assert query(roster_db,"SELECT (a.new_values::jsonb->>'added')::int,(a.new_values::jsonb->>'updated')::int,(a.new_values::jsonb->>'skipped')::int,u.status FROM uploaded_by u JOIN audit a ON a.affected_table='uploaded_by' AND a.action_type='roster_upload' AND a.affected_record_id=u.upload_id WHERE u.upload_id=%s",(identical,))==[(0,0,1,'superseded')]
    assert first!=second

def test_term_transition_empty_and_older_import(roster_db):
    first=import_list()
    empty=import_list([['','A','','B','a@example.edu']],year='2027-2028')
    assert query(roster_db,'SELECT status FROM uploaded_by WHERE upload_id=%s',(first,))==[('active',)]
    assert query(roster_db,'SELECT status FROM uploaded_by WHERE upload_id=%s',(empty,))==[('superseded',)]
    import_list(year='2027-2028')
    assert query(roster_db,'SELECT status FROM uploaded_by WHERE upload_id=%s',(first,))==[('superseded',)]
    with pytest.raises(ValueError,match='Older-term'):
        import_list()

def test_import_rollback_including_supersession(roster_db,monkeypatch):
    first=import_list()
    monkeypatch.setattr(roster,'log_audit',lambda *a,**k: (_ for _ in ()).throw(RuntimeError('audit failure')))
    with pytest.raises(RuntimeError):
        import_list(year='2027-2028')
    assert query(roster_db,'SELECT upload_id,status FROM uploaded_by')==[(first,'active')]
    assert query(roster_db,'SELECT COUNT(*) FROM roster')==[(1,)]

@pytest.mark.parametrize('actor',[1,2])
def test_import_allowed_roles(roster_db,actor):
    assert import_list(actor=actor)

@pytest.mark.parametrize('actor',[None,3,4])
def test_import_denies_other_roles(roster_db,actor):
    with pytest.raises(PermissionError):
        import_list(actor=actor)
    assert query(roster_db,'SELECT COUNT(*) FROM uploaded_by')==[(0,)]

def test_claimed_and_pending_reserved_rows_protected(roster_db):
    import_list()
    assert student()[1]['decision']=='approved'
    upload=import_list([['001234','Changed','','Name','changed@example.edu']])
    assert query(roster_db,"SELECT (new_values::jsonb->>'updated')::int,(new_values::jsonb->>'skipped')::int FROM audit WHERE action_type='roster_upload' AND affected_table='uploaded_by' AND affected_record_id=%s",(upload,))==[(0,1)]
    import_list([['00002','A','','B','other@example.edu']])
    query(roster_db,"INSERT INTO signup(user_id,status,roster_id) SELECT 3,'pending',roster_id FROM roster WHERE university_no='00002'")
    upload=import_list([['00002','Changed','','Name','new@example.edu']])
    assert query(roster_db,"SELECT (new_values::jsonb->>'updated')::int,(new_values::jsonb->>'skipped')::int FROM audit WHERE action_type='roster_upload' AND affected_table='uploaded_by' AND affected_record_id=%s",(upload,))==[(0,1)]

def test_full_match_approves_and_consumes_proof(roster_db):
    import_list()
    token=proof('ADA@example.edu')
    ok,result=student(email=' ADA@EXAMPLE.EDU ',signup_verification_id=token)
    assert ok and result['decision']=='approved'
    assert query(roster_db,'''SELECT u.account_status,u.role_id,s.roster_id IS NOT NULL,s.status,s.method,
        s.reviewed_by,s.contact_id IS NOT NULL,s.requested_at IS NOT NULL,s.decided_at IS NOT NULL,s.registration_date IS NOT NULL
        FROM "user" u JOIN signup s USING(user_id) WHERE s.signup_id=%s''',(result['signup_id'],))==[('active',17,True,'approved','auto',None,True,True,True,True)]
    assert not signup_verification.signup_email_is_verified(token,'ada@example.edu')
    assert query(roster_db,"SELECT COUNT(*) FROM audit WHERE action_type='automatic_signup_decision'")==[(1,)]
    assert query(roster_db,'SELECT COUNT(*) FROM signup_decision_delivery')==[(1,)]
    assert auth.sign_in('ada','Secure123')[0]

@pytest.mark.parametrize('mismatch',['email','number','type','inactive','missing'])
def test_nonmatches_are_rejected_without_claim(roster_db,mismatch):
    if mismatch!='missing':
        import_list()
    if mismatch=='type':
        query(roster_db,"UPDATE roster SET person_type='Faculty'")
    if mismatch=='inactive':
        query(roster_db,"UPDATE uploaded_by SET status='superseded'")
    ok,result=student(email='other@example.edu' if mismatch=='email' else 'ada@example.edu',number='99999' if mismatch=='number' else '001234')
    assert ok and result['decision']=='rejected'
    assert query(roster_db,'SELECT u.account_status,s.roster_id FROM "user" u JOIN signup s USING(user_id) WHERE s.signup_id=%s',(result['signup_id'],))==[('rejected',None)]
    assert auth.sign_in('ada','Secure123')[0] is None
    assert not auth.review_verification_request(result['signup_id'],'approved','',1)[0]
    assert not users.set_account_status(5,'active',1)[0]

def test_number_alone_and_consumed_proof_cannot_approve(roster_db):
    import_list()
    assert not auth.create_user('A','','B','001234','ada@example.edu','ada','Secure123',requested_role='Student')[0]
    token=proof('wrong@example.edu')
    assert not student(signup_verification_id=token)[0]
    assert query(roster_db,'SELECT COUNT(*) FROM signup')==[(0,)]

def test_resubmission_reuses_identity_and_keeps_history(roster_db):
    ok,first=student()
    assert ok and first['decision']=='rejected'
    import_list()
    assert query(roster_db,'SELECT status FROM signup')==[('rejected',)]
    assert not student()[0]
    ok,second=student(resubmit=True)
    assert ok and second['decision']=='approved'
    assert query(roster_db,'SELECT COUNT(DISTINCT user_id),COUNT(*) FROM signup')==[(1,2)]
    assert query(roster_db,'SELECT status FROM signup ORDER BY signup_id')==[('rejected',),('approved',)]
    assert not student(resubmit=True)[0]

def test_continuing_student_gets_new_roster_row_not_new_account(roster_db):
    import_list(); assert student()[1]['decision']=='approved'
    original=query(roster_db,"SELECT roster_id FROM signup WHERE user_id=5 AND status='approved'")[0][0]
    import_list(year='2027-2028')
    assert query(roster_db,'SELECT COUNT(*) FROM roster')==[(2,)]
    assert query(roster_db,"SELECT s.roster_id,u.account_status FROM signup s JOIN \"user\" u USING(user_id) WHERE user_id=5 AND s.status='approved'")==[(original,'active')]
    assert not student(username='second')[0]

def test_simultaneous_claim_only_one_account(roster_db):
    import_list()
    tokens=[proof('ada@example.edu'),proof('ada@example.edu')]
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda item:student(username=item[0],signup_verification_id=item[1]),zip(('first','second'),tokens)))
    assert sum(ok for ok,_ in results)==1
    assert query(roster_db,'SELECT COUNT(*) FROM signup')==[(1,)]

def test_signup_waits_for_supersession(roster_db,monkeypatch):
    import_list(); token=proof('ada@example.edu')
    entered,release=Event(),Event()
    real=roster.log_audit
    def hold(*args,**kwargs):
        if args[2]=='roster_upload':
            entered.set()
            assert release.wait(10)
        return real(*args,**kwargs)
    monkeypatch.setattr(roster,'log_audit',hold)
    with ThreadPoolExecutor(2) as pool:
        importing=pool.submit(import_list,[['99999','New','','Student','new@example.edu']],'2027-2028')
        assert entered.wait(10)
        signing=pool.submit(student,signup_verification_id=token)
        try:
            assert not signing.done()
        finally:
            release.set()
        importing.result()
        assert signing.result()[1]['decision']=='rejected'

def test_decision_failure_rolls_back_every_record_and_proof(roster_db,monkeypatch):
    import_list(); token=proof('ada@example.edu')
    monkeypatch.setattr(roster,'log_audit',lambda *a,**k: (_ for _ in ()).throw(RuntimeError('failure')))
    assert not student(signup_verification_id=token)[0]
    assert query(roster_db,'SELECT COUNT(*) FROM signup')==[(0,)]
    assert query(roster_db,'SELECT COUNT(*) FROM contact')==[(0,)]
    assert signup_verification.signup_email_is_verified(token,'ada@example.edu')

def test_email_failure_keeps_approval_and_retries(roster_db,feature_app,monkeypatch):
    import_list(); result=student()[1]
    feature_app.config.update(MAIL_DEFAULT_SENDER='capre@example.edu')
    Mail(feature_app)
    from app import mail
    monkeypatch.setattr(mail,'send',lambda message: (_ for _ in ()).throw(OSError('offline')))
    with feature_app.app_context():
        assert signup_delivery.deliver_pending(result['signup_id'])==0
    assert query(roster_db,"SELECT account_status FROM \"user\" WHERE user_id=5")==[('active',)]
    assert query(roster_db,'SELECT attempts,delivered_at FROM signup_decision_delivery')==[(1,None)]
    query(roster_db,"UPDATE signup_decision_delivery SET available_at=CURRENT_TIMESTAMP")
    sent=[]; monkeypatch.setattr(mail,'send',sent.append)
    with feature_app.app_context():
        assert signup_delivery.deliver_pending(result['signup_id'])==1
        assert signup_delivery.deliver_pending(result['signup_id'])==0
    assert len(sent)==1

def test_faculty_manual_and_legacy_pending_unchanged(roster_db):
    ok,_=auth.create_user('F','','Teacher','1234','faculty@example.edu','teacher','Secure123',requested_role='Faculty')
    assert ok
    assert query(roster_db,"SELECT u.account_status,s.roster_id FROM signup s JOIN \"user\" u USING(user_id) WHERE user_id=5 ORDER BY signup_id DESC LIMIT 1")==[('pending',None)]
    signup=query(roster_db,'SELECT signup_id FROM signup')[0][0]
    assert auth.review_verification_request(signup,'approved','',1)[0]
    assert query(roster_db,'SELECT account_status FROM "user" WHERE user_id=3')==[('active',)]

@pytest.mark.parametrize('actor,allowed',[(1,True),(2,True),(3,False),(4,False),(None,False)])
def test_roster_routes_and_templates_require_active_privileged_user(roster_db,feature_app,actor,allowed):
    client=feature_app.test_client()
    with client.session_transaction() as state:
        if actor: state['user_id']=actor
    for path in ('/roster','/roster/template/csv','/roster/template/xlsx'):
        assert client.get(path).status_code==(200 if allowed else 403)
    if allowed:
        query(roster_db,"UPDATE \"user\" SET account_status='deactivated' WHERE user_id=%s",(actor,))
        assert client.get('/roster').status_code==403

def test_migration_is_recorded_and_normalized_constraints_enforced(roster_db):
    assert NEW in migration_runner.migration_status()['applied']
    assert migration_runner.upgrade_database()==[]
    query(roster_db,"UPDATE \"user\" SET university_no=' id-001 ' WHERE user_id=3")
    with pytest.raises(psycopg2.errors.UniqueViolation):
        query(roster_db,"UPDATE \"user\" SET university_no='ID-001' WHERE user_id=4")

@pytest.mark.parametrize('roster_db',['historical'],indirect=True)
@pytest.mark.parametrize('conflict',['numbers','pending_upload','pending_reservation'])
def test_migration_preflight_refuses_history_without_changing_it(roster_db,conflict):
    if conflict=='numbers':
        query(roster_db,"UPDATE \"user\" SET university_no=' id-001 ' WHERE user_id=3")
        query(roster_db,"UPDATE \"user\" SET university_no='ID-001' WHERE user_id=4")
    else:
        query(roster_db,"INSERT INTO uploaded_by(file_name,status) VALUES('old.csv',%s)",('pending' if conflict=='pending_upload' else 'superseded',))
        if conflict=='pending_reservation':
            query(roster_db,"INSERT INTO roster(upload_id,university_no,person_type,contact) VALUES(1,'001','Student','a@example.edu')")
            query(roster_db,"INSERT INTO signup(user_id,status,roster_id) VALUES(3,'pending',1),(4,'pending',1)")
    with pytest.raises(psycopg2.Error):
        migration_runner.upgrade_database()
    assert NEW not in migration_runner.migration_status()['applied']
    assert query(roster_db,"SELECT COUNT(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='uploaded_by' AND column_name='file_type'")==[(0,)]
    if conflict=='pending_upload':
        assert query(roster_db,'SELECT status FROM uploaded_by')==[('pending',)]

@pytest.mark.parametrize('roster_db',['historical'],indirect=True)
def test_explicitly_superseded_unclassified_history_remains_ineligible(roster_db):
    query(roster_db,"INSERT INTO uploaded_by(file_name,status) VALUES('historical.csv','superseded')")
    query(roster_db,"INSERT INTO roster(upload_id,university_no,person_type,contact) VALUES(1,'001234','Student','ada@example.edu')")
    assert migration_runner.upgrade_database()==[NEW]
    assert query(roster_db,'SELECT status,file_type FROM uploaded_by')==[('superseded',None)]
    assert student()[1]['decision']=='rejected'

def test_reserved_and_ambiguous_matches_fail_closed(roster_db):
    first=import_list()
    query(roster_db,"INSERT INTO signup(user_id,status,roster_id) SELECT 3,'pending',roster_id FROM roster")
    assert student()[1]['decision']=='rejected'
    with pytest.raises(psycopg2.errors.UniqueViolation):
        query(roster_db,"INSERT INTO signup(user_id,status,roster_id) SELECT 4,'pending',roster_id FROM roster")
    # A separate number duplicated across active same-term uploads is ambiguous.
    other=import_list([['00002','A','','B','other@example.edu']])
    query(roster_db,"INSERT INTO roster(upload_id,university_no,person_type,contact) VALUES(%s,'00002','Student','other@example.edu')",(first,))
    upload=import_list([['00002','Changed','','Name','other@example.edu']])
    assert query(roster_db,"SELECT (new_values::jsonb->>'updated')::int,(new_values::jsonb->>'skipped')::int FROM audit WHERE action_type='roster_upload' AND affected_table='uploaded_by' AND affected_record_id=%s",(upload,))==[(0,1)]
    assert student(email='other@example.edu',number='00002',username='other')[1]['decision']=='rejected'
    assert other!=upload

def test_cor_required_and_privileged_public_roles_rejected(roster_db):
    import_list(); token=proof('ada@example.edu')
    for role in ('Admin','Capstone Professor','System Administrator'):
        assert not auth.create_user('A','','B','001234','ada@example.edu','ada','Secure123',
            requested_role=role,signup_verification_id=token,cor_filename='cor.pdf')[0]
    assert not auth.create_user('A','','B','001234','ada@example.edu','ada','Secure123',
        requested_role='Student',signup_verification_id=token)[0]
    assert signup_verification.signup_email_is_verified(token,'ada@example.edu')

def test_missing_header_and_oversized_files_leave_no_upload(roster_db,monkeypatch):
    with pytest.raises(ValueError):
        roster.import_roster(file([],['email']),'Class','2026-2027','1',1)
    from app.services import roster_import
    monkeypatch.setattr(roster_import,'MAX_BYTES',10)
    with pytest.raises(ValueError):
        import_list()
    assert query(roster_db,'SELECT COUNT(*) FROM uploaded_by')==[(0,)]

def test_import_type_ignores_spreadsheet_role(roster_db):
    upload=FileStorage(stream=BytesIO(b'university_no,first_name,last_name,email,person_type\n001,A,B,a@example.edu,Admin\n'),filename='students.csv')
    roster.import_roster(upload,'Class','2026-2027','1',1)
    assert query(roster_db,'SELECT person_type FROM roster')==[('Student',)]

def test_result_detail_post_and_template_permissions_and_csrf(roster_db,feature_app):
    upload=import_list()
    record=query(roster_db,'SELECT roster_id FROM roster')[0][0]
    client=feature_app.test_client()
    for actor in (3,4):
        with client.session_transaction() as state:
            state.update(user_id=actor,role_name='Admin',role_id=3)
        for path in (f'/roster/uploads/{upload}',f'/roster/records/{record}'):
            assert client.get(path).status_code==403
        assert client.post('/roster',data={}).status_code==403
    with client.session_transaction() as state:
        state.update(user_id=1)
    assert client.get(f'/roster/uploads/{upload}').status_code==200
    assert client.get(f'/roster/records/{record}').status_code==200
    feature_app.config['WTF_CSRF_ENABLED']=True
    assert client.post('/roster',data={}).status_code==400

def test_new_delivery_storage_has_rls_and_no_public_privileges(roster_db):
    assert query(roster_db,"SELECT relrowsecurity FROM pg_class WHERE oid='signup_decision_delivery'::regclass")==[(True,)]
    assert query(roster_db,"SELECT COUNT(*) FROM information_schema.table_privileges WHERE table_schema='public' AND table_name='signup_decision_delivery' AND grantee='PUBLIC'")==[(0,)]

def test_authenticated_resubmission_can_correct_number_and_preserve_credentials(roster_db):
    from werkzeug.security import generate_password_hash
    assert student(number='99999')[1]['decision']=='rejected'
    original=query(roster_db,'SELECT user_id,username_id,password_id FROM slug')[0]
    legacy_password='Existing-Legacy-123456'
    query(roster_db,'UPDATE ror SET password=%s WHERE password_id=%s',(generate_password_hash(legacy_password),original[2]))
    import_list()
    ok,result=auth.create_user('Corrected','','Name','001234','ada@example.edu','ada',legacy_password,
        requested_role='Student',resubmit=True,signup_verification_id=proof('ada@example.edu'),cor_filename='new-cor.pdf')
    assert ok and result['decision']=='approved'
    assert query(roster_db,'SELECT user_id,username_id,password_id FROM slug')==[original]
    assert query(roster_db,'SELECT university_no FROM "user" WHERE user_id=%s',(original[0],))==[('001234',)]
    assert query(roster_db,'SELECT COUNT(*) FROM signup')==[(2,)]
    assert auth.sign_in('ada',legacy_password)[0]

def test_resubmission_invalid_proof_rolls_back_new_attempt(roster_db):
    token=proof('ada@example.edu')
    assert student(signup_verification_id=token)[1]['decision']=='rejected'
    import_list()
    assert not student(signup_verification_id=token,resubmit=True)[0]
    assert query(roster_db,'SELECT status FROM signup')==[('rejected',)]
    assert query(roster_db,"SELECT u.account_status,s.roster_id FROM signup s JOIN \"user\" u USING(user_id) WHERE user_id=5 ORDER BY signup_id DESC LIMIT 1")==[('rejected',None)]

def test_current_signup_reservation_is_not_treated_as_another_applicant(roster_db,monkeypatch):
    import_list()
    real=roster.decide_student
    def reserve_then_decide(cursor,user_id,signup_id,*args):
        cursor.execute('UPDATE signup SET roster_id=(SELECT roster_id FROM roster LIMIT 1) WHERE signup_id=%s',(signup_id,))
        return real(cursor,user_id,signup_id,*args)
    monkeypatch.setattr(roster,'decide_student',reserve_then_decide)
    assert student()[1]['decision']=='approved'

@pytest.mark.parametrize('actor',[1,2])
def test_http_upload_redirects_to_persistent_result(roster_db,feature_app,actor,monkeypatch):
    client=feature_app.test_client()
    with client.session_transaction() as state:
        state['user_id']=actor
    upload=file()
    response=client.post('/roster',data={'master_list':(upload.stream,upload.filename),'class_name':'A',
        'academic_year':'2026-2027','semester':'1'})
    assert response.status_code==302 and '/roster/preview/' in response.location
    preview_url=response.location
    assert query(roster_db,'SELECT COUNT(*) FROM uploaded_by')==[(0,)]
    assert b'Estimated:' in client.get(preview_url).data
    token=preview_url.rsplit('/',1)[-1]
    confirmed=client.post('/roster/confirm/'+token,data={'candidate':'0'})
    assert confirmed.status_code==302
    result=client.get(confirmed.location)
    assert result.status_code==200 and b'Added 1, updated 0, skipped 0' in result.data
    retry=client.get('/signup?resubmit=1')
    assert b'maxlength="256"' in retry.data and b'COR PDF remains required' in retry.data
    monkeypatch.setattr(roster_stage,'create_stage',lambda *a,**k: (_ for _ in ()).throw(PermissionError('revoked')))
    upload=file()
    assert client.post('/roster',data={'master_list':(upload.stream,upload.filename),'class_name':'A',
        'academic_year':'2026-2027','semester':'1'}).status_code==403

@pytest.mark.parametrize('email',['a..b@example.edu','a@example..edu','Name <a@example.edu>'])
def test_invalid_email_syntax_is_skipped(email):
    accepted,skipped=parse_upload(file([['001234','A','','B',email]]))
    assert not accepted and skipped==[{'row':2,'source':{'table':1,'row':2},'reason':'Invalid email.'}]

@pytest.mark.parametrize('eligible',[True,False])
def test_public_signup_reports_actual_decision_and_email_failure_is_post_commit(roster_db,feature_app,monkeypatch,eligible):
    from tests.test_original_branch_features import signup_data
    from app import mail
    if eligible: import_list()
    client=feature_app.test_client()
    with client.session_transaction() as state:
        state['signup_email_verification_id']=proof('ada@example.edu')
        state['signup_verified_email']='ada@example.edu'
    feature_app.config['MAIL_DEFAULT_SENDER']='capre@example.edu'
    Mail(feature_app)
    expected='active' if eligible else 'rejected'
    def unavailable(message):
        # Separate connection must observe committed account state before send.
        assert query(roster_db,'SELECT account_status FROM "user" WHERE user_id=5')==[(expected,)]
        raise OSError('SMTP unavailable')
    monkeypatch.setattr(mail,'send',unavailable)
    data=signup_data()
    data.update(email='ada@example.edu',username='ada',student_no='001234')
    response=client.post('/signup',data=data)
    assert response.status_code==302
    content=client.get(response.location).data
    assert (b'You can sign in now' if eligible else b'Eligibility could not be confirmed') in content
    assert query(roster_db,'SELECT attempts,delivered_at FROM signup_decision_delivery')==[(1,None)]
    assert query(roster_db,'SELECT cor_filename IS NOT NULL FROM "user" WHERE user_id=5')==[(True,)]
    with client.session_transaction() as state:
        assert 'signup_email_verification_id' not in state
