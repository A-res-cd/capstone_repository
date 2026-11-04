"""Private expiring extraction payloads and transactional confirmation receipts."""
from contextlib import closing
from hashlib import sha256
import hmac
from pathlib import Path
from uuid import uuid4
from psycopg2.extras import RealDictCursor, Json
from app.db.connection import db_connect
from app.db import roster
from app.services.roster_import import MAX_BYTES, normalize_candidate
from app.utils.document_processing import process_document

class StageExpired(ValueError):
    pass

def binding_hash(binding):
    if not isinstance(binding,str) or len(binding)<32:
        raise PermissionError('Open the upload page in your current session.')
    return sha256(binding.encode()).hexdigest()

def create_stage(upload,class_name,academic_year,semester,actor_id,binding,update_upload_id=None):
    roster.check_actor(actor_id)
    hashed=binding_hash(binding)
    metadata=roster.validate_metadata(class_name,academic_year,semester)
    roster.prepare_masterlist(actor_id,metadata,update_upload_id)
    extension=Path(upload.filename or '').suffix.lower()
    if extension not in ('.xlsx','.docx','.pdf','.csv'):
        raise ValueError('Use XLSX, DOCX, text-based PDF or CSV; legacy XLS/DOC are unsupported.')
    content=upload.stream.read(MAX_BYTES+1)
    if not content or len(content)>MAX_BYTES:
        raise ValueError('Choose a nonempty document up to 5 MiB.')
    extracted=process_document(content,extension,operation='student_list')
    payload={'metadata':metadata,'file_name':Path(upload.filename).name,'update_upload_id':update_upload_id,**extracted}
    token=str(uuid4())
    with closing(db_connect()) as conn,conn.cursor() as cursor:
        roster.require_actor(cursor,actor_id)
        cursor.execute('DELETE FROM roster_import_stage WHERE expires_at<clock_timestamp()')
        cursor.execute('''INSERT INTO roster_import_stage(stage_id,actor_id,session_hash,payload,expires_at)
            VALUES(%s,%s,%s,%s,CURRENT_TIMESTAMP+INTERVAL '30 minutes')''',(token,actor_id,hashed,Json(payload)))
        conn.commit()
    return token

def load_stage(cursor,token,actor_id,binding,lock=False):
    roster.require_actor(cursor,actor_id)
    cursor.execute('''SELECT *,expires_at>clock_timestamp() AS valid FROM roster_import_stage WHERE stage_id=%s'''
                   +(' FOR UPDATE' if lock else ''),(token,))
    stage=cursor.fetchone()
    if not stage:
        raise LookupError('Preview not found.')
    if str(stage['actor_id'])!=str(actor_id) or not hmac.compare_digest(stage['session_hash'],binding_hash(binding)):
        raise PermissionError('Preview belongs to a different uploader/session.')
    if not stage['valid']:
        raise StageExpired('Preview expired. Upload the document again.')
    return stage

def select_candidate(stage,candidate_id):
    candidates=stage['payload']['candidates']
    if candidate_id is None and len(candidates)==1:
        return candidates[0]
    found=next((row for row in candidates if row['id']==str(candidate_id)),None)
    if not found:
        raise ValueError('Select the intended worksheet/table from the preview.')
    return found

def preview(token,actor_id,binding,candidate_id=None):
    with closing(db_connect()) as conn,conn.cursor(cursor_factory=RealDictCursor) as cursor:
        stage=load_stage(cursor,token,actor_id,binding)
        if stage['upload_id']:
            return {'completed_upload_id':stage['upload_id']}
        candidates=stage['payload']['candidates']
        result={'stage_id':token,'expires_at':stage['expires_at'],'payload':stage['payload'],'candidates':candidates}
        if candidate_id is None and len(candidates)>1:
            return result
        selected=select_candidate(stage,candidate_id)
        rows,skipped,display=normalize_candidate(selected)
        roster.lock_student_roster(cursor)
        _,updates,_,summary=roster.plan_import(cursor,rows,skipped,stage['payload']['metadata'],actor_id,stage['payload'].get('update_upload_id'))
        reasons={str(row['source']):row['reason'] for row in summary['skipped_rows']}
        updated={str(row['source']) for _,row in updates}
        for row in display:
            row['issue']=reasons.get(str(row['source']))
            row['estimated']='skipped' if row['issue'] else 'updated' if str(row['source']) in updated else 'added'
        result.update(selected=selected,rows=display,summary=summary)
        return result

def confirm(token,actor_id,binding,candidate_id=None):
    with closing(db_connect()) as conn,conn.cursor(cursor_factory=RealDictCursor) as cursor:
        try:
            roster.lock_student_roster(cursor)
            stage=load_stage(cursor,token,actor_id,binding,lock=True)
            if stage['upload_id']:
                return stage['payload'].get('confirmed_result') or roster.import_result(cursor,stage['upload_id'])['result']
            selected=select_candidate(stage,candidate_id)
            rows,skipped,_=normalize_candidate(selected)
            payload=stage['payload']
            roster.prepare_masterlist(actor_id,payload['metadata'],payload.get('update_upload_id'))
            result=roster.apply_import(cursor,rows,skipped,payload['metadata'],payload['file_name'],actor_id,payload['format'],payload.get('update_upload_id'))
            cursor.execute("UPDATE roster_import_stage SET upload_id=%s,payload=%s::jsonb WHERE stage_id=%s",(result['upload_id'],Json({'confirmed_result':result}),token))
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise

def purge_expired():
    with closing(db_connect()) as conn,conn.cursor() as cursor:
        cursor.execute('DELETE FROM roster_import_stage WHERE expires_at<clock_timestamp()')
        removed=cursor.rowcount
        conn.commit()
        return removed
