from flask import Blueprint, render_template

pages = Blueprint("pages", __name__)


@pages.route("/archive")
def browse():
    return render_template("global/explore_archive.html", hide_nav=False)

@pages.route("/user-info")
def user_info():
    return render_template("global/user_information.html", hide_nav=False)