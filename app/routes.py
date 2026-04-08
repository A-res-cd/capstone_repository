from flask import Blueprint, render_template, request, redirect, url_for, session
from .authentication_db.mysql import register_user, login_user
from .capstone_db.mongodb import get_all_capstones, insert_capstone, delete_capstone

main = Blueprint("main", __name__)

@main.route("/")
def home():
    return render_template("index.html")