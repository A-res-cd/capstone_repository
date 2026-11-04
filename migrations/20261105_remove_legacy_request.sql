-- 20261105_remove_legacy_request.sql
-- CAPRE ERD: retire BOTH public.request and public.capstone_requests.
-- This migration is NEW. Do NOT edit any previously applied migration.
-- Only apply AFTER Codex removes both tables' application and test dependencies,
-- a verified backup is taken, and deletion/retention of historical rows is approved.
--
-- Safety: refuse to drop EITHER populated table. No implicit data deletion.
-- If historical rows exist, STOP. Export/archive and obtain explicit authorization
-- before proceeding. DO NOT bypass checks by truncating records.
DO $retire_request_tables$
DECLARE
    table_name TEXT;
    existing_rows BIGINT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['request', 'capstone_requests']
    LOOP
        IF to_regclass(format('public.%I', table_name)) IS NOT NULL THEN
            -- Hold through both DROP statements so a concurrent writer cannot
            -- insert historical data after the empty-table check.
            EXECUTE format('LOCK TABLE public.%I IN ACCESS EXCLUSIVE MODE', table_name);
            EXECUTE format('SELECT count(*) FROM public.%I', table_name) INTO existing_rows;
            IF existing_rows > 0 THEN
                RAISE EXCEPTION
                    'Refusing to remove public.%: % existing rows; archive/retain data and obtain explicit deletion approval first.',
                    table_name, existing_rows;
            END IF;
        END IF;
    END LOOP;
END
$retire_request_tables$;

-- RESTRICT fails rather than silently dropping dependent views or other objects.
-- Investigate and update any dependencies instead of changing to CASCADE.
DROP TABLE IF EXISTS public."request" RESTRICT;
DROP TABLE IF EXISTS public.capstone_requests RESTRICT;
