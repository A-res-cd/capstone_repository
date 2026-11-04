-- Direct masterlist ownership; unknown historical uploaders remain Admin-only.
BEGIN;

ALTER TABLE uploaded_by ADD COLUMN uploader_user_id INT
    REFERENCES "user"(user_id) ON DELETE SET NULL;

UPDATE uploaded_by u SET uploader_user_id = (
    SELECT a.user_id FROM audit a JOIN "user" p ON p.user_id=a.user_id
    WHERE a.action_type='roster_upload' AND a.affected_table='uploaded_by'
        AND a.affected_record_id=u.upload_id
    ORDER BY a.audit_id LIMIT 1
);

CREATE INDEX uploaded_by_uploader_idx ON uploaded_by(uploader_user_id,uploaded_at DESC,upload_id DESC);

COMMIT;
