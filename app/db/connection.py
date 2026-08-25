"""
Database connection helper. Every other app/db/*.py module imports
db_connect() from here — this is the one place PostgreSQL connection
params are read from Config.
"""
import psycopg2
from config import Config


def db_connect():
    conn = psycopg2.connect(
        host=Config.PG_HOST,
        port=Config.PG_PORT,
        user=Config.PG_USER,
        password=Config.PG_PASSWORD,
        database=Config.PG_DB,
    )

    return conn

