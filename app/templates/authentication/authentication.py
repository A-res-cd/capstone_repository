from flask import Blueprint, flash, render_template, request, redirect, url_for, session
from flask_mail import Mail, Message
from app import mail

auth = Blueprint("auth", __name__, url_prefix="/auth")

