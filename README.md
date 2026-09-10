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

UPLOAD_MANUSCRIPT_FOLDER = app/static/uploads/manuscripts
UPLOAD_REGISTRATION_FOLDER = app/static/uploads/registration

# Required for automatic OCR of scanned COR files.
# Install the Windows engine separately from:
# https://github.com/UB-Mannheim/tesseract/wiki
TESSERACT_CMD = C:\Program Files\Tesseract-OCR\tesseract.exe

# 6. Run the app
flask run
or
python run.py

# 7. Run the tests
pytest app/test/test_cor_extractor.py app/test/test_cor_pdf.py -q

# 8. When done, deactivate environment
deactivate

## COR upload and automatic extraction

Signup accepts a Certificate of Registration as a PDF. The upload appears first
in the form and attempts to extract the registration number, student number,
first name, middle name, and last name. Extracted values remain editable before
account creation. The sample COR test is stored at
`app/static/uploads/registration/Sapin_Aaries_M._3e7f3448731c472d93c9912b893e73ac.pdf`.

The sample COR is image-based, so Tesseract OCR must be installed for automatic
extraction. `pytesseract` in `requirements.txt` is only the Python wrapper. If
Tesseract is unavailable, the form shows a warning and allows manual entry.
