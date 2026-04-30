from flask import Blueprint, render_template, request, redirect, url_for, session
from .variables.variable import get_nav_links

main = Blueprint("main", __name__)

@main.route("/")
def home():
    return render_template("index.html", hide_nav=True)

@main.route("/login")
def login():
    return render_template("login.html", hide_nav=True)

@main.route("/dashboard")
def dashboard():
    role = "Admin"
    nav_links = get_nav_links(role)
    return render_template("dashboard.html", nav_links=nav_links, hide_nav=False)

@main.route("/user_role")
def user():
    role = "User"
    nav_links = get_nav_links(role)
    return render_template("dashboard.html", nav_links=nav_links, hide_nav=False)

@main.route("/logout")
def logout():
    return render_template("index.html", hide_nav=True)