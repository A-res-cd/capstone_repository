"""Authentication sessions routes and local helpers."""
from . import auth
from flask import flash, render_template, request, redirect, url_for, session
import psycopg2.extras
from app.db.connection import db_connect
from app.db.auth import sign_in, sign_out
from app.routes.forms import SigninForm


@auth.route("/signin", methods=["GET", "POST"])
def signin():
    locked_until = None
    form = SigninForm()

    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        device_ip = request.headers.get("X-Forwarded-For", request.remote_addr)

        user, error = sign_in(username, password, device_ip=device_ip)

        if error:
            if "locked" in error.lower():
                locked_until = None
                conn = db_connect()
                cur = conn.cursor(
                    cursor_factory=psycopg2.extras.RealDictCursor)
                cur.execute("""
                    SELECT u.locked_until
                    FROM "user" u
                    JOIN slug sl ON sl.user_id = u.user_id AND sl.is_current = TRUE
                    JOIN kappa k ON k.username_id = sl.username_id
                    WHERE k.username = %s
                    LIMIT 1
                """, (username,))
                row = cur.fetchone()
                cur.close()
                conn.close()
                if row and row["locked_until"]:
                    locked_until = row["locked_until"].isoformat()
            else:
                flash(error, "error")

            return render_template("authentication/signin.html", form=form, hide_nav=True, hide_header=True, locked_until=locked_until)
        if user:
            session["user_id"]    = user["user_id"]
            session["username"]   = user["username"]
            session["role_id"]    = user["role_id"]
            session["role_name"]  = user["role_name"]
            session["first_name"] = user.get("user_first_name", "")
            session["last_name"]  = user.get("user_last_name", "")
            session["log_in_id"]  = user.get("log_in_id")

            if user["role_id"] == 3:    # Admin
                return redirect(url_for("admin.analytics"))
            elif user["role_id"] == 4:  # Capstone Professor
                return redirect(url_for("admin.manage_users"))
            elif user["role_id"] == 2:  # Faculty
                return redirect(url_for("pages.browse"))
            else:                        # Student (1)
                return redirect(url_for("pages.browse"))
        else:
            flash(error, "error")

    return render_template("authentication/signin.html", form=form, hide_nav=True, hide_header=True)


@auth.route("/logout")
def logout():
    user_id = session.get("user_id")
    if user_id:
        device_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        sign_out(user_id, device_ip=device_ip)

    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.signin"))


def get_current_user(user_id):
    """Get the current logged-in user from the session."""
    if not user_id:
        return None

    conn = db_connect()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT u.user_id, u.first_name, u.middle_name, u.last_name, u.email, u.role_id, r.role_name, u.locked_until
        FROM "user" u
        JOIN role r ON u.role_id = r.role_id
        WHERE u.user_id = %s
        LIMIT 1
    """, (user_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    return user
