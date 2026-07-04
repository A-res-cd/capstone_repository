import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # MongoDB connection
    MONGO_URI = os.getenv("MONGO_URI")

    # MySQL connection (must be edited to match your MySQL configuration)
    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DB = os.getenv("MYSQL_DB", "users")

    SECRET_KEY = os.getenv("SECRET_KEY", "aresDaGreatSecretKey")