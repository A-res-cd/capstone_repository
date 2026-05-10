from flask import Blueprint, flash, render_template, request, redirect, url_for, session
from flask_mail import Mail, Message
from app import mail

pages = Blueprint("pages", __name__, url_prefix="/pages")

