"""Shared lifecycle lock, imports and authoritative student decisions."""
from contextlib import closing
import json
import re
from psycopg2.extras import RealDictCursor, execute_values
from werkzeug.utils import secure_filename
from app.db.connection import db_connect
from app.db.audit import log_audit
from app.services.roster_import import parse_upload, normalize_number, normalize_email, valid_number, valid_email

SEMESTERS = {1: 'First', 2: 'Second', 3: 'Summer'}

def lock_student_roster(cursor):
    # First lock for imports and signup; also protects identities with no row yet.
    cursor.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', ('capre.student-roster',))

def require_actor(cursor, actor_id):
    cursor.execute('''SELECT 1 FROM "user" u JOIN role r USING(role_id)
        WHERE u.user_id=%s AND u.account_status='active' AND r.role_name IN ('Admin','Capstone Professor')''', (actor_id,))
    if not cursor.fetchone():
        raise PermissionError('Active Admin or Capstone Professor access required.')

def check_actor(actor_id):
    with closing(db_connect()) as conn, conn.cursor() as cursor:
        require_actor(cursor, actor_id)

def validate_metadata(class_name,academic_year,semester):
    class_name=(class_name or '').strip()
    academic_year=(academic_year or '').strip()
    year=re.fullmatch(r'(\d{4})-(\d{4})',academic_year)
    semester=SEMESTERS.get(int(semester),None) if str(semester).strip().isdigit() else semester
    if not class_name or len(class_name)>150 or not year or int(year[2])!=int(year[1])+1 or not 1900<=int(year[1])<=2200 or semester not in SEMESTERS.values():
        raise ValueError('Supply class, consecutive academic year YYYY-YYYY, and First/Second/Summer semester.')
    return {'class_name':class_name,'academic_year':academic_year,'semester':semester}

def term(metadata):
    return int(metadata['academic_year'].split('-')[0]),next(k for k,v in SEMESTERS.items() if v==metadata['semester'])

def plan_import(cursor,rows,skipped,metadata):
    """Read-only plan shared by preview and confirmation; caller holds lifecycle lock."""
    current=term(metadata)
    cursor.execute("SELECT upload_id,academic_year,semester FROM uploaded_by WHERE file_type='student_list' AND status='active' ORDER BY upload_id FOR UPDATE")
    active=cursor.fetchall()
    if active and current<max(term(row) for row in active):
        raise ValueError('Older-term uploads are not allowed; existing eligibility unchanged.')
    same=[row['upload_id'] for row in active if term(row)==current]
    older=[row['upload_id'] for row in active if term(row)<current]
    numbers=[row['university_no'] for row in rows]
    cursor.execute("""SELECT r.* FROM roster r WHERE upload_id=ANY(%s) AND person_type='Student'
        AND UPPER(BTRIM(university_no))=ANY(%s) ORDER BY roster_id FOR UPDATE""",(same,numbers))
    existing_by_number={}
    for row in cursor.fetchall():
        existing_by_number.setdefault(normalize_number(row['university_no']),[]).append(row)
    ids=[row['roster_id'] for group in existing_by_number.values() for row in group]
    cursor.execute("SELECT roster_id FROM signup WHERE roster_id=ANY(%s) AND status IN ('pending','approved')",(ids,))
    protected={row['roster_id'] for row in cursor.fetchall()}
    cursor.execute("""SELECT UPPER(BTRIM(university_no)) AS number FROM "user"
        WHERE account_status IS DISTINCT FROM 'rejected' AND UPPER(BTRIM(university_no))=ANY(%s)""",(numbers,))
    claimed_numbers={row['number'] for row in cursor.fetchall()}
    inserts,updates=[],[]
    skipped=list(skipped)
    for row in rows:
        existing=existing_by_number.get(row['university_no'],[])
        reason=None
        if len(existing)>1:
            reason='Ambiguous active identity; explicit correction required.'
        elif existing:
            old=existing[0]
            if old['roster_id'] in protected or row['university_no'] in claimed_numbers:
                reason='Identity claimed or reserved; unchanged.'
            elif (old['user_first_name'],old['user_middle_name'] or '',old['user_last_name'],normalize_email(old['contact']))==(row['first_name'],row['middle_name'],row['last_name'],row['email']):
                reason='Identical details; unchanged.'
            else:
                updates.append((old,row))
        else:
            inserts.append(row)
        if reason:
            skipped.append({'row':row['source_row'],'source':row['source'],'reason':reason})
    result={'added':len(inserts),'updated':len(updates),'skipped':len(skipped),
            'skipped_rows':sorted(skipped,key=lambda row:row['row']),
            'message':'Import saved.' if inserts or updates else 'No changes; usable uploads were not superseded.'}
    return inserts,updates,older,result

def apply_import(cursor,rows,skipped,metadata,file_name,actor_id,physical_format):
    lock_student_roster(cursor)
    require_actor(cursor,actor_id)
    metadata=validate_metadata(metadata['class_name'],metadata['academic_year'],metadata['semester'])
    inserts,updates,older,result=plan_import(cursor,rows,skipped,metadata)
    changed=bool(inserts or updates)
    cursor.execute("""INSERT INTO uploaded_by(file_name,class_name,academic_year,semester,status,file_type)
        VALUES(%s,%s,%s,%s,%s,'student_list') RETURNING upload_id""",
        (secure_filename(file_name)[:255],metadata['class_name'],metadata['academic_year'],metadata['semester'],'active' if changed else 'superseded'))
    upload_id=cursor.fetchone()['upload_id']
    if inserts:
        execute_values(cursor,"""INSERT INTO roster(upload_id,university_no,person_type,user_first_name,user_middle_name,user_last_name,contact)
            VALUES %s""",[(upload_id,row['university_no'],'Student',row['first_name'],row['middle_name'],row['last_name'],row['email']) for row in inserts],page_size=500)
    for old,row in updates:
        cursor.execute("""UPDATE roster SET user_first_name=%s,user_middle_name=%s,user_last_name=%s,contact=%s,
            updated_at=CURRENT_TIMESTAMP WHERE roster_id=%s""",(row['first_name'],row['middle_name'],row['last_name'],row['email'],old['roster_id']))
        log_audit(cursor,actor_id,'roster_correction','roster',old['roster_id'],
            old_values=json.dumps({k:old[k] for k in ('upload_id','university_no','user_first_name','user_middle_name','user_last_name','contact')}),
            new_values=json.dumps({'import_upload_id':upload_id,'source':row['source'],'details':{k:row[k] for k in ('university_no','first_name','middle_name','last_name','email')}}))
    if changed and older:
        cursor.execute("UPDATE uploaded_by SET status='superseded' WHERE upload_id=ANY(%s)",(older,))
    result.update(upload_id=upload_id,uploader_id=actor_id,physical_format=physical_format,
                  superseded_upload_ids=older if changed else [])
    log_audit(cursor,actor_id,'roster_upload','uploaded_by',upload_id,new_values=json.dumps(result))
    return result

def import_roster(upload,class_name,academic_year,semester,actor_id):
    """Trusted internal entry point. HTTP imports require staged confirmation."""
    from pathlib import Path
    rows,skipped=parse_upload(upload)
    metadata=validate_metadata(class_name,academic_year,semester)
    with closing(db_connect()) as conn,conn.cursor(cursor_factory=RealDictCursor) as cursor:
        try:
            result=apply_import(cursor,rows,skipped,metadata,upload.filename or 'student-list',actor_id,Path(upload.filename or '').suffix.lstrip('.').lower())
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise

def decorate_upload(row):
    try:
        summary=json.loads(row.pop('audit_summary') or '{}')
    except (ValueError,TypeError):
        summary={}
    row['result']=summary
    for key in ('added','updated','skipped'):
        row[key+'_count']=summary.get(key)
    row['uploader']=row.get('uploader') or ('Former user #'+str(summary['uploader_id']) if summary.get('uploader_id') else 'Historical uploader unknown')
    return row

UPLOAD_READ_SQL="""SELECT u.*,a.new_values AS audit_summary,CONCAT_WS(' ',p.user_first_name,p.user_last_name) AS uploader
    FROM uploaded_by u LEFT JOIN LATERAL (SELECT user_id,new_values FROM audit
      WHERE action_type='roster_upload' AND affected_table='uploaded_by' AND affected_record_id=u.upload_id
      ORDER BY audit_id DESC LIMIT 1) a ON TRUE LEFT JOIN "user" p ON p.user_id=a.user_id """

def import_result(cursor,upload_id):
    cursor.execute(UPLOAD_READ_SQL+' WHERE u.upload_id=%s',(upload_id,))
    row=cursor.fetchone()
    return decorate_upload(row) if row else None

def decide_student(cursor,user_id,signup_id,number,email,contact_id,verification_id):
    """Consume ownership proof and decide eligibility in the caller's transaction."""
    lock_student_roster(cursor)
    from app.db.signup_verification import consume_email_verification
    number,email=normalize_number(number),normalize_email(email)
    if not valid_number(number) or not valid_email(email):
        raise ValueError('Invalid student identity.')
    if not consume_email_verification(cursor,verification_id,email):
        raise ValueError('Verify your email again before submitting.')
    cursor.execute('''SELECT r.roster_id,r.contact FROM roster r JOIN uploaded_by u USING(upload_id)
        WHERE UPPER(BTRIM(r.university_no))=%s AND r.person_type='Student' AND u.file_type='student_list'
        AND u.status='active' ORDER BY r.roster_id FOR UPDATE OF r,u''',(normalize_number(number),))
    matches = cursor.fetchall()
    selected = matches[0] if len(matches)==1 and normalize_email(matches[0]['contact'])==normalize_email(email) else None
    reason = 'No unique active student roster number/email match.'
    if selected:
        cursor.execute('''SELECT 1 FROM "user" WHERE user_id<>%s AND UPPER(BTRIM(university_no))=%s
            UNION ALL SELECT 1 FROM signup WHERE roster_id=%s AND status IN ('pending','approved') AND signup_id<>%s LIMIT 1''',
            (user_id,normalize_number(number),selected['roster_id'],signup_id))
        if cursor.fetchone():
            selected = None
            reason = 'Roster identity already claimed or reserved.'
    roster_id = selected['roster_id'] if selected else None
    decision = 'approved' if selected else 'rejected'
    cursor.execute("SELECT role_id FROM role WHERE role_name='Student'")
    role = cursor.fetchone()
    if not role:
        raise ValueError('Student role unavailable.')
    cursor.execute('''UPDATE signup SET status=%s,method='auto',reviewed_by=NULL,roster_id=%s,contact_id=%s,
        sub_person_type='student',decided_at=CURRENT_TIMESTAMP,reason=%s,attempt_count=1 WHERE signup_id=%s''',
        (decision,roster_id,contact_id,None if selected else reason,signup_id))
    cursor.execute('''UPDATE "user" SET account_status=%s,role_id=%s WHERE user_id=%s''',
        ('active' if selected else 'rejected',role['role_id'],user_id))
    log_audit(cursor,user_id,'automatic_signup_decision','signup',signup_id,old_values='pending',
        new_values=json.dumps({'status':decision,'reason':None if selected else reason,'roster_id':roster_id,'user_id':user_id}))
    cursor.execute('INSERT INTO signup_decision_delivery(signup_id,recipient_email) VALUES(%s,%s)',(signup_id,normalize_email(email)))
    return decision

def read_roster(actor_id,search='',upload_id=None):
    with closing(db_connect()) as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        require_actor(cursor,actor_id)
        cursor.execute(UPLOAD_READ_SQL+' ORDER BY u.uploaded_at DESC,u.upload_id DESC LIMIT 100')
        history=[decorate_upload(row) for row in cursor.fetchall()]
        upload=import_result(cursor,upload_id) if upload_id is not None else None
        query = '%'+search.replace('!','!!').replace('%','!%').replace('_','!_')[:100]+'%'
        cursor.execute('''SELECT r.*,u.academic_year,u.semester,u.status FROM roster r JOIN uploaded_by u USING(upload_id)
            WHERE (%s::int IS NULL OR r.upload_id=%s) AND (r.university_no ILIKE %s ESCAPE '!' OR r.contact ILIKE %s ESCAPE '!'
            OR CONCAT_WS(' ',r.user_first_name,r.user_last_name) ILIKE %s ESCAPE '!') ORDER BY r.roster_id DESC LIMIT 100''',
            (upload_id,upload_id,query,query,query))
        return history,cursor.fetchall(),upload

def get_record(actor_id,roster_id):
    with closing(db_connect()) as conn,conn.cursor(cursor_factory=RealDictCursor) as cursor:
        require_actor(cursor,actor_id)
        cursor.execute('''SELECT r.*,u.class_name,u.academic_year,u.semester,u.status FROM roster r
            JOIN uploaded_by u USING(upload_id) WHERE r.roster_id=%s''',(roster_id,))
        return cursor.fetchone()
