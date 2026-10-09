-- Run in Supabase SQL Editor against the CAPRE application database.
-- Creates four active demo accounts; skips existing usernames without resetting them.
-- Passwords use Werkzeug hashes, matching the Flask login implementation.
BEGIN;

DO $$
DECLARE
    account RECORD;
    selected_role_id INT;
    new_user_id INT;
    new_username_id INT;
    new_password_id INT;
BEGIN
    FOR account IN
        SELECT * FROM (VALUES
        ('Student', 'Student', 'Demo', 'Student', 'DEMO-STU-001', 'student@example.com', 'scrypt:32768:8:1$0TgpxAic7mjIjHzo$9ec1c428b18d9d7b1563713774e48ad63ad4bae65e870c8edda5ef34de55407f18ea9b381a0c2278176da58ceac203385a837959e24fc97c2a741410559c7647'),
        ('Faculty', 'Faculty', 'Demo', 'Faculty', NULL, 'faculty@example.com', 'scrypt:32768:8:1$dPDH0xsYEgZge01f$8724aa271c0ec27edceae1a5162ea3083f16ce5b25c0cff19f6bdc007a130d57796de7520f45a6b4f74a9e6f78825fa3d68ca796889442fcb52b1cb3e9ef7b75'),
        ('Capstone Professor', 'CapProf', 'Demo', 'Professor', NULL, 'professor@example.com', 'scrypt:32768:8:1$tAtYAQM9aNwexRfD$cd0480f6216dfdc30878c3a8561aeec7e1f6d0ed73926331cdb06a9addbec03869a1786d24a1dab44dffd7b6130916f2a41962f798e5cad11f6593ed979bddd8'),
        ('Admin', 'Admin', 'Demo', 'Admin', NULL, 'admin@example.com', 'scrypt:32768:8:1$VEqZNd5RIs9IxNJL$c7b6271d5ca30db25df49492a72709d736399f5fcf142414b16de0dc7b946e9e862524ee421a29cba8c7af9613aec6941347cfe1fb1e975ce864f411e20b5a2a')
        ) AS seed(role_name, username, first_name, last_name, university_no, email, password_hash)
    LOOP
        IF EXISTS (SELECT 1 FROM public.kappa WHERE username = account.username) THEN
            RAISE NOTICE 'Skipping existing username: %', account.username;
            CONTINUE;
        END IF;

        SELECT role_id INTO selected_role_id
        FROM public.role WHERE role_name = account.role_name;
        IF selected_role_id IS NULL THEN
            RAISE EXCEPTION 'Required role missing: %', account.role_name;
        END IF;

        INSERT INTO public."user" (
            role_id, user_first_name, user_last_name, university_no,
            account_status, preferred_contact
        ) VALUES (
            selected_role_id, account.first_name, account.last_name,
            account.university_no, 'active', 'email'
        ) RETURNING user_id INTO new_user_id;

        INSERT INTO public.kappa (username)
        VALUES (account.username)
        RETURNING username_id INTO new_username_id;

        INSERT INTO public.ror (password, updated_at, previous_password_id)
        VALUES (account.password_hash, CURRENT_TIMESTAMP, NULL)
        RETURNING password_id INTO new_password_id;

        INSERT INTO public.slug (
            username_id, password_id, user_id, assigned_at, updated_at, is_current
        ) VALUES (
            new_username_id, new_password_id, new_user_id,
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, TRUE
        );

        INSERT INTO public.contact (
            user_id, contact_type, contact_value, is_primary, created_at
        ) VALUES (new_user_id, 'email', account.email, TRUE, CURRENT_TIMESTAMP);

        INSERT INTO public.signup (user_id, registration_date)
        VALUES (new_user_id, CURRENT_TIMESTAMP);

        INSERT INTO public.audit (
            user_id, action_type, affected_table, affected_record_id,
            new_values, action_timestamp
        ) VALUES (
            NULL, 'seed_role_account', 'user', new_user_id,
            account.username || ' (' || account.role_name || ')', CURRENT_TIMESTAMP
        );
    END LOOP;
END $$;

COMMIT;
