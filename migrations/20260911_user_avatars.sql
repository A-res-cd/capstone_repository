-- Normalized, private profile image metadata.
CREATE TABLE IF NOT EXISTS user_avatar (
    user_avatar_id SERIAL PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,
    storage_key VARCHAR(255) NOT NULL UNIQUE,
    original_name VARCHAR(255),
    mime_type VARCHAR(50) NOT NULL,
    file_size INT NOT NULL,
    width INT,
    height INT,
    uploaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_user_avatar_user
        FOREIGN KEY (user_id)
        REFERENCES "user"(user_id)
        ON DELETE CASCADE
);
