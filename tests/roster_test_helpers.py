"""Historical manual-review fixtures, distinct from new public student signup.

Use the retained faculty credential chain to build a pre-roster account fixture,
then explicitly classify the fixture as a legacy pending Student. New automatic
student signup tests use real verified proofs and roster matches instead.
"""
def create_legacy_account(module,*args,**kwargs):
    kwargs['requested_role']='Faculty'
    ok,result=module.create_user(*args,**kwargs)
    if ok:
        email=args[4].strip().lower()
        with module.db_connect() as conn,conn.cursor() as cursor:
            cursor.execute('''UPDATE "user" SET role_id=(SELECT role_id FROM role WHERE role_name='Student')
                WHERE user_id=(SELECT user_id FROM contact WHERE contact_type='email' AND LOWER(contact_value)=%s LIMIT 1)
                RETURNING user_id''',(email,))
            user_id=cursor.fetchone()[0]
            cursor.execute("UPDATE signup SET sub_person_type='student' WHERE user_id=%s",(user_id,))
    return ok,result
