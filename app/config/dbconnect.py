import re
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config


class DABOL_CONEK:
    def __init__(self):
        self.conn = psycopg2.connect(
            host=Config.PG_HOST,
            port=Config.PG_PORT,
            user=Config.PG_USER,
            password=Config.PG_PASSWORD,
            database=Config.PG_DB,
        )
        self.mithrix = self.conn.cursor(
            cursor_factory=psycopg2.extras.DictCursor)

    def connect_db(self):
        return DABOL_CONEK()
