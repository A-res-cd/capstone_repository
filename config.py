import os
from dotenv import load_dotenv

load_dotenv()

class Config:

    # MySQL connection (must be edited to match your MySQL configuration)
    MYSQL_HOST = os.getenv("MYSQL_HOST")
    MYSQL_USER = os.getenv("MYSQL_USER")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
    MYSQL_DB = os.getenv("MYSQL_DB")

    # PostgreSQL connection used by app/config/mysql.py
    PG_HOST = os.getenv("PG_HOST")
    PG_PORT = int(os.getenv("PG_PORT", "5432"))
    PG_USER = os.getenv("PG_USER")
    PG_PASSWORD = os.getenv("PG_PASSWORD")
    PG_DB = os.getenv("PG_DB")

    SECRET_KEY = os.getenv("SECRET_KEY", "aresDaGreatSecretKey")