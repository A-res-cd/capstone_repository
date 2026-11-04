"""Failed automatic student verification can be reviewed by the owning professor."""
from pathlib import Path

import pytest

from app.db import auth, verification_documents
from app.routes.admin import users as user_routes
from tests.test_roster_automatic_signup import roster_db, isolated_database, feature_app, import_list, student, query
from tests.test_original_branch_features import pdf_bytes


@pytest.fixture
def rejected_student(roster_db,feature_app,monkeypatch):
    monkeypatch.setattr(verification_documents,'db_connect',roster_db)
    import_list(actor=2)
    ok,result=student(email='different@example.edu')
    assert ok and result['decision']=='rejected'
    folder=Path(feature_app.config['UPLOAD_REGISTRATION_FOLDER'])
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'registration.pdf').write_bytes(pdf_bytes())
    monkeypatch.setattr(user_routes,'_send_verification_email',lambda *args: True)
    return result['signup_id']


def professor_client(app,ident):
    client=app.test_client()
    with client.session_transaction() as state:
        state.update(user_id=ident,role_name='Capstone Professor')
    return client


def test_owner_can_review_matching_rejected_student_without_schema_changes(roster_db,feature_app,rejected_student):
    ident=rejected_student
    assert [row['request_id'] for row in auth.get_pending_verifications(2)]==[ident]
    assert [row['request_id'] for row in auth.get_pending_verifications(1)]==[ident]
    details=verification_documents.get_verification_details(ident,2)
    assert details['manual_student_review'] and 'Verified email does not match' in details['verification_reason']
    client=professor_client(feature_app,2)
    assert client.get('/manage_users').status_code==200
    response=client.get(f'/manage_users/verify/{ident}/details')
    assert response.status_code==200 and response.json['document_url']
    assert client.get(f'/manage_users/verify/{ident}/document').status_code==200
    assert client.post(f'/manage_users/verify/{ident}',data={'decision':'approved'}).status_code==302
    assert query(roster_db,'''SELECT s.status,s.method,s.reviewed_by,s.roster_id IS NOT NULL,u.account_status
        FROM signup s JOIN "user" u USING(user_id) WHERE signup_id=%s''',(ident,))==[('approved','manual',2,True,'active')]
    assert auth.get_pending_verifications(2)==[]
    assert auth.sign_in('ada','Secure123')[0]
    assert not auth.review_verification_request(ident,'approved','',2)[0]


def test_other_professor_cannot_list_read_or_decide(roster_db,feature_app,rejected_student):
    other=query(roster_db,"INSERT INTO \"user\"(role_id,account_status) VALUES(47,'active') RETURNING user_id")[0][0]
    ident=rejected_student
    assert auth.get_pending_verifications(other)==[]
    assert verification_documents.get_verification_details(ident,other) is None
    assert verification_documents.get_verification_document(ident,other) is None
    client=professor_client(feature_app,other)
    for suffix in ('details','document'):
        assert client.get(f'/manage_users/verify/{ident}/{suffix}').status_code==404
    assert client.post(f'/manage_users/verify/{ident}',data={'decision':'approved'}).status_code==404
    assert not auth.review_verification_request(ident,'approved','',other)[0]


def test_manual_review_rechecks_eligibility_document_and_email_proof(roster_db,feature_app,rejected_student):
    ident=rejected_student
    path=Path(feature_app.config['UPLOAD_REGISTRATION_FOLDER'])/'registration.pdf'
    path.unlink()
    client=professor_client(feature_app,2)
    client.post(f'/manage_users/verify/{ident}',data={'decision':'approved'})
    assert query(roster_db,'SELECT status FROM signup WHERE signup_id=%s',(ident,))==[('rejected',)]
    path.write_bytes(pdf_bytes())
    query(roster_db,'UPDATE signup_email_verifications SET consumed_at=NULL')
    query(roster_db,"DELETE FROM audit WHERE action_type='automatic_signup_decision'")
    assert not auth.review_verification_request(ident,'approved','',2)[0]
    query(roster_db,"UPDATE uploaded_by SET status='superseded'")
    assert auth.get_pending_verifications(2)==[]
    assert not auth.review_verification_request(ident,'approved','',2)[0]


def test_manual_rejection_is_not_relisted(roster_db,rejected_student):
    assert auth.review_verification_request(rejected_student,'rejected','COR does not match student identity.',2)[0]
    assert auth.get_pending_verifications(2)==[]
    assert not auth.review_verification_request(rejected_student,'approved','',2)[0]


def test_review_uses_durable_signup_evidence_after_email_code_cleanup(roster_db,rejected_student):
    query(roster_db,'DELETE FROM signup_email_verifications')
    assert auth.review_verification_request(rejected_student,'approved','',2)[0]


def test_admin_can_reject_legacy_pending_but_professor_cannot_view_unmatched(roster_db,monkeypatch):
    monkeypatch.setattr(verification_documents,'db_connect',roster_db)
    query(roster_db,"UPDATE \"user\" SET account_status='pending' WHERE user_id=3")
    ident=query(roster_db,"INSERT INTO signup(user_id,status,method) VALUES(3,'pending','manual') RETURNING signup_id")[0][0]
    assert [row['request_id'] for row in auth.get_pending_verifications(1)]==[ident]
    assert auth.get_pending_verifications(2)==[]
    assert verification_documents.get_verification_details(ident,2) is None
    assert auth.review_verification_request(ident,'rejected','Verify email and resubmit against the masterlist.',1)[0]
