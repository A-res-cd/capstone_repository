"""Periodic worker: python scripts/deliver_signup_decisions.py; no web scheduler."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from flask import Flask
from app import mail
from config import Config
from app.db.signup_delivery import deliver_pending
from app.db.roster_stage import purge_expired

def main():
    app = Flask(__name__)
    app.config.from_object(Config)
    mail.init_app(app)
    with app.app_context():
        print('Expired roster previews removed:',purge_expired())
        print('Delivered:',deliver_pending())

if __name__ == '__main__':
    main()
