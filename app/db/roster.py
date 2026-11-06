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
    cursor.execute('''SELECT r.role_name FROM "user" u JOIN role r USING(role_id)
        WHERE u.user_id=%s AND u.account_status='active' AND r.role_name IN ('Admin','Capstone Professor')''', (actor_id,))
    actor = cursor.fetchone()
    if not actor:
        raise PermissionError('Active Admin or Capstone Professor access required.')
    return actor['role_name'] if isinstance(actor,dict) else actor[0]


def _roster_owner(cursor,actor_id):
    return None if require_actor(cursor,actor_id)=='Admin' else actor_id

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

def _update_target(cursor,upload_id,actor_id,metadata=None):
    owner=_roster_owner(cursor,actor_id)
    cursor.execute('''SELECT * FROM uploaded_by WHERE upload_id=%s AND status='active'
        AND (%s::int IS NULL OR uploader_user_id=%s) FOR UPDATE''',(upload_id,owner,owner))
    target=cursor.fetchone()
    if not target:
        raise ValueError('Choose an active masterlist you are allowed to update.')
    if metadata and any(str(target[key]).strip().casefold()!=str(metadata[key]).strip().casefold()
                        for key in ('class_name','academic_year','semester')):
        raise ValueError('An update must keep the existing class, academic year and semester.')
    return target


def prepare_masterlist(actor_id,metadata,update_upload_id=None):
    with closing(db_connect()) as conn,conn.cursor(cursor_factory=RealDictCursor) as cursor:
        if update_upload_id is not None:
            return dict(_update_target(cursor,update_upload_id,actor_id,metadata))
        require_actor(cursor,actor_id)
        cursor.execute('''SELECT 1 FROM uploaded_by WHERE uploader_user_id=%s AND status='active'
            AND LOWER(BTRIM(class_name))=LOWER(BTRIM(%s)) AND academic_year=%s AND semester=%s''',
            (actor_id,metadata['class_name'],metadata['academic_year'],metadata['semester']))
        if cursor.fetchone():
            raise ValueError('This class already has an active masterlist. Use Update masterlist in Upload history.')


def plan_import(cursor,rows,skipped,metadata,actor_id,update_upload_id=None):
    """Read-only plan shared by preview and confirmation; caller holds lifecycle lock."""
    current=term(metadata)
    owner=_roster_owner(cursor,actor_id)
    cursor.execute("""SELECT upload_id,academic_year,semester FROM uploaded_by
        WHERE file_type='student_list' AND status='active' AND (%s::int IS NULL OR uploader_user_id=%s)
        ORDER BY upload_id FOR UPDATE""",(owner,owner))
    active=cursor.fetchall()
    if active and current<max(term(row) for row in active):
        raise ValueError('Older-term uploads are not allowed; existing eligibility unchanged.')
    same=[row['upload_id'] for row in active if term(row)==current]
    older=[row['upload_id'] for row in active if term(row)<current]
    target_owner=owner
    if update_upload_id is not None:
        target_owner=_update_target(cursor,update_upload_id,actor_id,metadata)['uploader_user_id']
        same=[update_upload_id]
        older=[]
    numbers=[row['university_no'] for row in rows]
    foreign_numbers=set()
    same_owner_numbers=set()
    if owner is not None or update_upload_id is not None:
        cursor.execute('''SELECT UPPER(BTRIM(r.university_no)) AS number,u.uploader_user_id FROM roster r
            JOIN uploaded_by u USING(upload_id) WHERE r.person_type='Student' AND u.status='active'
            AND ((%s::int IS NOT NULL AND u.upload_id<>%s) OR (%s::int IS NULL AND u.uploader_user_id IS DISTINCT FROM %s))
            AND UPPER(BTRIM(r.university_no))=ANY(%s)''',(update_upload_id,update_upload_id,update_upload_id,owner,numbers))
        for match in cursor.fetchall():
            if update_upload_id is not None and match['uploader_user_id']==target_owner:
                same_owner_numbers.add(match['number'])
            else:
                foreign_numbers.add(match['number'])
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
        if row['university_no'] in foreign_numbers:
            reason='Student belongs to another active masterlist; administrator review required.'
        elif len(existing)>1:
            reason='Ambiguous active identity; explicit correction required.'
        elif not existing and row['university_no'] in same_owner_numbers:
            reason='Student already appears in another active masterlist you own; update that list instead.'
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

def apply_import(cursor,rows,skipped,metadata,file_name,actor_id,physical_format,update_upload_id=None):
    lock_student_roster(cursor)
    require_actor(cursor,actor_id)
    metadata=validate_metadata(metadata['class_name'],metadata['academic_year'],metadata['semester'])
    inserts,updates,older,result=plan_import(cursor,rows,skipped,metadata,actor_id,update_upload_id)
    changed=bool(inserts or updates)
    if update_upload_id is not None:
        upload_id=update_upload_id
        cursor.execute('UPDATE uploaded_by SET file_name=%s,uploaded_at=CURRENT_TIMESTAMP WHERE upload_id=%s',
                       (secure_filename(file_name)[:255],upload_id))
        result['message']='Masterlist updated. Existing students absent from this file were kept.'
    else:
        cursor.execute("""INSERT INTO uploaded_by(file_name,class_name,academic_year,semester,status,file_type,uploader_user_id)
            VALUES(%s,%s,%s,%s,%s,'student_list',%s) RETURNING upload_id""",
            (secure_filename(file_name)[:255],metadata['class_name'],metadata['academic_year'],metadata['semester'],'active' if changed else 'superseded',actor_id))
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
      ORDER BY audit_id DESC LIMIT 1) a ON TRUE LEFT JOIN "user" p ON p.user_id=u.uploader_user_id """

def import_result(cursor,upload_id,owner=None):
    cursor.execute(UPLOAD_READ_SQL+' WHERE u.upload_id=%s AND (%s::int IS NULL OR u.uploader_user_id=%s)',(upload_id,owner,owner))
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
    reason = ('Student number is not in an active masterlist.' if not matches else
              'Student number appears more than once in active masterlists; professor review required.' if len(matches)>1 else
              'Verified email does not match the email in the masterlist. Ask your professor to correct it, then resubmit.')
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

REGISTRATION_COLUMNS="""CASE WHEN account.account_status IS NULL THEN 'Not registered'
    WHEN account.account_status='active' AND account.signup_status='approved' THEN 'Verified registered'
    WHEN account.account_status='rejected' OR account.signup_status='rejected' THEN 'Rejected - resubmit required'
    WHEN account.signup_status='pending' THEN 'Pending verification'
    ELSE 'Account ' || account.account_status END AS registration_status,
    account.reason AS registration_reason"""
REGISTRATION_JOIN='''LEFT JOIN LATERAL (
    SELECT p.account_status,s.status AS signup_status,s.reason FROM "user" p JOIN role role USING(role_id)
    LEFT JOIN LATERAL (SELECT status,reason FROM signup WHERE user_id=p.user_id ORDER BY signup_id DESC LIMIT 1) s ON TRUE
    WHERE role.role_name='Student' AND UPPER(BTRIM(p.university_no))=UPPER(BTRIM(r.university_no)) LIMIT 1
) account ON TRUE'''


def read_roster(actor_id,search='',upload_id=None,registered_only=False,class_name=''):
    with closing(db_connect()) as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        owner=_roster_owner(cursor,actor_id)
        cursor.execute(UPLOAD_READ_SQL+' WHERE (%s::int IS NULL OR u.uploader_user_id=%s) ORDER BY u.uploaded_at DESC,u.upload_id DESC LIMIT 100',(owner,owner))
        history=[decorate_upload(row) for row in cursor.fetchall()]
        upload=import_result(cursor,upload_id,owner) if upload_id is not None else None
        query = '%'+search.replace('!','!!').replace('%','!%').replace('_','!_')[:100]+'%'
        cursor.execute(f'''SELECT r.*,u.class_name,u.academic_year,u.semester,u.status,{REGISTRATION_COLUMNS}
            FROM roster r JOIN uploaded_by u USING(upload_id) {REGISTRATION_JOIN}
            WHERE (%s::int IS NULL OR u.uploader_user_id=%s) AND (%s::int IS NULL OR r.upload_id=%s)
            AND (NOT %s OR (u.status='active' AND account.account_status='active' AND account.signup_status='approved'))
            AND (%s='' OR LOWER(BTRIM(u.class_name))=LOWER(BTRIM(%s)))
            AND (r.university_no ILIKE %s ESCAPE '!' OR r.contact ILIKE %s ESCAPE '!'
            OR CONCAT_WS(' ',r.user_first_name,r.user_last_name) ILIKE %s ESCAPE '!') ORDER BY r.roster_id DESC LIMIT 100''',
            (owner,owner,upload_id,upload_id,registered_only,class_name.strip(),class_name.strip(),query,query,query))
        return history,cursor.fetchall(),upload


def read_class_masterlists(actor_id):
    with closing(db_connect()) as conn,conn.cursor(cursor_factory=RealDictCursor) as cursor:
        owner=_roster_owner(cursor,actor_id)
        cursor.execute(f'''SELECT r.*,u.class_name,u.academic_year,u.semester,u.status,u.uploader_user_id,
            CONCAT_WS(' ',uploader.user_first_name,uploader.user_last_name) AS uploader,{REGISTRATION_COLUMNS}
            FROM roster r JOIN uploaded_by u USING(upload_id) {REGISTRATION_JOIN}
            LEFT JOIN "user" uploader ON uploader.user_id=u.uploader_user_id
            WHERE r.person_type='Student' AND (%s::int IS NULL OR u.uploader_user_id=%s)
            ORDER BY LOWER(COALESCE(u.class_name,'')),u.academic_year DESC,u.semester,u.uploader_user_id,
                r.user_last_name,r.user_first_name,r.roster_id''',(owner,owner))
        groups={}
        for row in cursor.fetchall():
            key=(row['uploader_user_id'],(row['class_name'] or '').strip().casefold(),row['academic_year'],row['semester'])
            group=groups.setdefault(key,{'class_name':row['class_name'] or 'Uncategorized',
                'academic_year':row['academic_year'],'semester':row['semester'],'uploader':row['uploader'], 'students':[]})
            group['students'].append(row)
        return list(groups.values())

def roster_overview(actor_id):
    with closing(db_connect()) as conn,conn.cursor(cursor_factory=RealDictCursor) as cursor:
        owner=_roster_owner(cursor,actor_id)
        cursor.execute('''WITH students AS (
            SELECT DISTINCT UPPER(BTRIM(r.university_no)) AS number
            FROM roster r JOIN uploaded_by u USING(upload_id)
            WHERE r.person_type='Student' AND u.status='active' AND (%s::int IS NULL OR u.uploader_user_id=%s)
        ) SELECT COUNT(*) AS students,
            COUNT(*) FILTER (WHERE EXISTS (
                SELECT 1 FROM "user" p JOIN role role ON role.role_id=p.role_id
                WHERE UPPER(BTRIM(p.university_no))=students.number
                    AND role.role_name='Student' AND p.account_status='active'
                    AND EXISTS (SELECT 1 FROM signup s WHERE s.user_id=p.user_id AND s.status='approved')
            )) AS verified FROM students''',(owner,owner))
        return cursor.fetchone()


def get_record(actor_id,roster_id):
    with closing(db_connect()) as conn,conn.cursor(cursor_factory=RealDictCursor) as cursor:
        owner=_roster_owner(cursor,actor_id)
        cursor.execute(f'''SELECT r.*,u.class_name,u.academic_year,u.semester,u.status,{REGISTRATION_COLUMNS} FROM roster r
            JOIN uploaded_by u USING(upload_id) {REGISTRATION_JOIN}
            WHERE r.roster_id=%s AND (%s::int IS NULL OR u.uploader_user_id=%s)''',(roster_id,owner,owner))
        return cursor.fetchone()
