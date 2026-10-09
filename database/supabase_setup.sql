-- Apply after creating the final CAPRE schema and recording migrations.
-- Flask accesses PostgreSQL server-side; browser API roles must not read accounts.
DO $$
DECLARE
    capre_table TEXT;
BEGIN
    FOREACH capre_table IN ARRAY ARRAY[
        'role', 'user', 'kappa', 'ror', 'slug', 'login', 'logout', 'signup',
        'audit', 'contact', 'password_reset', 'program', 'specialization',
        'keyword', 'capstone', 'capstone_keyword', 'author', 'capauth',
        'request', 'capstone_view_history', 'schema_migration'
    ] LOOP
        EXECUTE FORMAT('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', capre_table);
        EXECUTE FORMAT('REVOKE ALL ON TABLE public.%I FROM anon, authenticated', capre_table);
    END LOOP;
END $$;

-- Private buckets: manuscript access and COR review stay behind Flask permissions.
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES
    ('capre-manuscripts', 'capre-manuscripts', FALSE, 26214400,
        ARRAY['application/pdf', 'application/msword',
              'application/vnd.openxmlformats-officedocument.wordprocessingml.document']),
    ('capre-registration', 'capre-registration', FALSE, 5242880,
        ARRAY['application/pdf']),
    ('capre-avatars', 'capre-avatars', FALSE, 2097152,
        ARRAY['image/png'])
ON CONFLICT (id) DO UPDATE SET
    public = EXCLUDED.public,
    file_size_limit = EXCLUDED.file_size_limit,
    allowed_mime_types = EXCLUDED.allowed_mime_types;

-- Lookup data only; no sample users or preset administrator password.
INSERT INTO public.role (role_name, role_level)
SELECT source.role_name, source.role_level
FROM (VALUES ('Student', 1), ('Faculty', 2), ('Admin', 3),
             ('Capstone Professor', 2)) AS source(role_name, role_level)
WHERE NOT EXISTS (SELECT 1 FROM public.role r WHERE r.role_name = source.role_name);

INSERT INTO public.program (program_code, program_name)
SELECT source.program_code, source.program_name
FROM (VALUES
    ('BSIT', 'Bachelor of Science in Information Technology'),
    ('BSDS', 'Bachelor of Science in Data Science')
) AS source(program_code, program_name)
WHERE NOT EXISTS (SELECT 1 FROM public.program p WHERE p.program_code = source.program_code);

INSERT INTO public.specialization (specialization_code, specialization_name)
SELECT source.specialization_code, source.specialization_name
FROM (VALUES
    ('DST', 'Database Systems Technology'),
    ('NST', 'Network Systems Technology'),
    ('WST', 'Web Systems Technology'),
    ('GENERAL', 'No specialization')
) AS source(specialization_code, specialization_name)
WHERE NOT EXISTS (
    SELECT 1 FROM public.specialization s
    WHERE s.specialization_code = source.specialization_code
);
