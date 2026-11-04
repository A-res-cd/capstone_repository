-- Multiple confirmed update previews may refer to the same class masterlist.
BEGIN;
ALTER TABLE roster_import_stage DROP CONSTRAINT roster_import_stage_upload_id_key;
CREATE INDEX roster_import_stage_upload_idx ON roster_import_stage(upload_id) WHERE upload_id IS NOT NULL;
COMMIT;
