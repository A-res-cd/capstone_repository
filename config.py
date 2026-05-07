import os
from dotenv import load_dotenv

load_dotenv()

class Config:

    # MySQL connection (must be edited to match your MySQL configuration)
    MYSQL_HOST = os.getenv("MYSQL_HOST")
    MYSQL_USER = os.getenv("MYSQL_USER")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
    MYSQL_DB = os.getenv("MYSQL_DB")

    SECRET_KEY = os.getenv("SECRET_KEY", "aresDaGreatSecretKey")