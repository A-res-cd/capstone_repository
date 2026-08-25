# 1. Clone the repo
git clone https://github.com/AresFrappe/capstone_repository.git
cd repository

# 2. Create virtual environment
# Windows
python -m venv venv

# 3. Activate virtual environment (run in terminal)
# Windows (CMD)
venv\Scripts\activate
# Windows (PowerShell)
venv\Scripts\Activate.ps1

# 4. Install dependencies
pip install -r requirements.txt

# 5. Create .env file
inside .env file put:
SECRET_KEY = your-secret-key

PG_HOST = localhost
PG_PORT = 5432
PG_USER = your-postgres-user
PG_PASSWORD = your-postgres-password
PG_DB = your-database-name

MAIL_SERVER = smtp.example.com
MAIL_PORT = 587
MAIL_USERNAME = your-email@example.com
MAIL_PASSWORD = your-email-password

UPLOAD_FOLDER = app/static/uploads

# 6. Run the app
flask run
or
python run.py

# 7. When done, deactivate environment
deactivate
