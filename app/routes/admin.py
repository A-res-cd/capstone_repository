from flask import Blueprint, render_template

admin = Blueprint("admin", __name__)


@admin.route("/analytics")
def analytics():
    return render_template("admin/analytics.html", hide_nav=False)


@admin.route("/manage_users")
def manage_users():
    return render_template("admin/manage_users.html", hide_nav=False)


@admin.route("/requests")
def requests():
    return render_template("admin/requests.html", hide_nav=False)


@admin.route("/repository")
def repository():
    return render_template("admin/repository.html", hide_nav=False)


# @admin.route("/add_capstone_record")
# def add_capstone_record():
#     return render_template("admin/add_capstone_record.html", hide_nav=False)
