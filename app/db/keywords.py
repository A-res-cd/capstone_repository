"""Normalized keyword storage and the display aggregate used by capstone queries."""

KEYWORD_JOIN = """
    LEFT JOIN LATERAL (
        SELECT STRING_AGG(kw.keyword_text, ', ' ORDER BY kw.keyword_text) AS capstone_keywords
        FROM capstone_keyword ck
        JOIN keyword kw ON kw.keyword_id = ck.keyword_id
        WHERE ck.capstone_id = c.capstone_id
    ) k ON TRUE
"""


def split_keywords(value):
    return sorted({part.strip().lower() for part in (value or '').split(',')
                   if part.strip()})


def insert_keyword_ids(cursor, value):
    keyword_ids = []
    for text in split_keywords(value):
        cursor.execute("""
            INSERT INTO keyword (keyword_text) VALUES (%s)
            ON CONFLICT (keyword_text) DO UPDATE SET keyword_text = EXCLUDED.keyword_text
            RETURNING keyword_id
        """, (text,))
        keyword_ids.append(cursor.fetchone()[0])
    return keyword_ids


def set_capstone_keywords(cursor, capstone_id, value):
    # Serialize replacements for the same capstone, including empty keyword sets.
    cursor.execute('SELECT capstone_id FROM capstone WHERE capstone_id = %s FOR UPDATE',
                   (capstone_id,))
    keyword_ids = insert_keyword_ids(cursor, value)
    cursor.execute('DELETE FROM capstone_keyword WHERE capstone_id = %s', (capstone_id,))
    for keyword_id in keyword_ids:
        cursor.execute("""
            INSERT INTO capstone_keyword (capstone_id, keyword_id) VALUES (%s, %s)
        """, (capstone_id, keyword_id))
