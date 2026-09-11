CREATE TABLE IF NOT EXISTS cor_registration (
    cor_registration_id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES "user"(user_id) ON DELETE CASCADE,
    registration_no VARCHAR(50) NOT NULL,
    academic_year VARCHAR(20),
    term VARCHAR(30),
    year_level SMALLINT,
    cor_filename VARCHAR(200) NOT NULL,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_cor_registration_user_number UNIQUE (user_id, registration_no)
);
