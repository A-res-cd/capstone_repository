BEGIN;

CREATE TABLE IF NOT EXISTS capstone_keyword (
    capstone_id INT REFERENCES capstone(capstone_id) ON DELETE CASCADE,
    keyword_id INT REFERENCES keyword(keyword_id) ON DELETE CASCADE,
    PRIMARY KEY (capstone_id, keyword_id)
);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'capstone' AND column_name = 'keyword_id'
    ) THEN
        LOCK TABLE capstone, keyword, capstone_keyword IN ACCESS EXCLUSIVE MODE;

        CREATE TEMP TABLE normalized_keyword_source ON COMMIT DROP AS
        SELECT DISTINCT k.keyword_id, LOWER(BTRIM(part)) AS keyword_text
        FROM keyword k
        CROSS JOIN LATERAL UNNEST(STRING_TO_ARRAY(k.capstone_keywords, ',')) AS parts(part)
        WHERE BTRIM(part) <> '';

        CREATE TEMP TABLE capstone_keyword_source ON COMMIT DROP AS
        SELECT DISTINCT c.capstone_id, s.keyword_text
        FROM capstone c
        JOIN normalized_keyword_source s ON s.keyword_id = c.keyword_id;

        ALTER TABLE capstone DROP COLUMN keyword_id;
        DELETE FROM keyword;
        ALTER TABLE keyword RENAME COLUMN capstone_keywords TO keyword_text;
        ALTER TABLE keyword
            ALTER COLUMN keyword_text SET NOT NULL,
            ADD CONSTRAINT keyword_text_unique UNIQUE (keyword_text),
            ADD CONSTRAINT keyword_text_normalized CHECK (
                keyword_text <> '' AND keyword_text = LOWER(BTRIM(keyword_text))
                AND POSITION(',' IN keyword_text) = 0
            );

        INSERT INTO keyword (keyword_text)
        SELECT DISTINCT keyword_text FROM normalized_keyword_source ORDER BY keyword_text;

        INSERT INTO capstone_keyword (capstone_id, keyword_id)
        SELECT s.capstone_id, k.keyword_id
        FROM capstone_keyword_source s
        JOIN keyword k ON k.keyword_text = s.keyword_text;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS capstone_keyword_keyword_idx ON capstone_keyword (keyword_id);

COMMIT;
