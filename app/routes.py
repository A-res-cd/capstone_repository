from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from .variables.variable import get_nav_links, get_role_meta, resolve_title
from .config.mysql import create_user, sign_in

main = Blueprint("main", __name__)

@main.app_context_processor
def inject_global_template_vars():
    role = session.get("role_name", "Admin")

    # 2. Get nav + role meta
    nav_links, nav_sections = get_nav_links(role)
    role_meta = get_role_meta(role)

    # 3. Resolve title automatically
    page_title = resolve_title(nav_sections, nav_links, request.path)

    return {
        "nav_links": nav_links,
        "nav_sections": nav_sections,
        "role_meta": role_meta,
        "page_title": page_title,
    }

## --- Landings & Auth routes ---

@main.route("/")
def home():
    return render_template("index.html", hide_nav=True)

@main.route("/signin", methods = ["GET", "POST"])
def signin():
    if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()
    
            # Validation
            errors = []
            if not username: errors.append("Username is required.")
            if not password: errors.append("Password is required.")
    
            if errors:
                for e in errors:
                    flash(e, "error")
                return render_template("authentication/signin.html",
                                    hide_nav=True, hide_header=True)
    
            # Capture device IP for login table
            device_ip = request.headers.get("X-Forwarded-For",
                        request.remote_addr)
    
            user, error = sign_in(username, password, device_ip=device_ip)
    
            if user:
                session["user_id"]   = user["user_id"]
                session["username"]  = user["username"]
                session["role_id"]   = user["role_id"]
                session["role_name"] = user["role_name"]
                return redirect(url_for("main.home"))
            else:
                flash(error, "error")
    
    return render_template("authentication/signin.html", hide_nav=True, hide_header=True)

@main.route('/signup', methods = ['GET', 'POST'])
def signup():
    if request.method == 'POST':
        first_name = request.form.get('first_name')
        middle_name = request.form.get('middle_name')
        last_name = request.form.get('last_name')
        university_no = request.form.get('university_no')
        email = request.form.get('email')
        username = request.form.get('username')
        password = request.form.get('password')

    
        success, message = create_user(
        first_name, middle_name, last_name, 
        university_no, email, username, password
        )
        if success:
            flash("Account created successfully! Please sign in.", "success")
            return redirect(url_for('main.signin'))
        else:
            flash(message, "danger")

            return render_template("authentication/signup.html", 
                hide_nav=True, hide_header=True, 
                form_data=request.form)

    return render_template("authentication/signup.html", hide_nav=True, hide_header=True, form_data={})

@main.route("/logout")
def logout():
    session.clear()
    return render_template("index.html", hide_nav=True, hide_header=True)

# forfot password
@main.route("/forgot_password")
def forgot_password():
    return render_template(
        "authentication/forgot_password.html",
        hide_nav=True,
        hide_header=True
    )



## --- Admin specific routes ---
@main.route("/analytics")
def admin_analytics():
    return render_template("admin/analytics.html", hide_nav=False)

@main.route("/manage_users")
def admin_manage_users():
    return render_template("admin/manage_users.html", hide_nav=False)

@main.route("/requests")
def admin_requests():
    return render_template("admin/requests.html", hide_nav=False)

