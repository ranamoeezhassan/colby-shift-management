from flask import render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User
import os
from dotenv import load_dotenv

from . import auth_bp

# Load in environment variables
load_dotenv()

@auth_bp.route('/', methods=['GET'])
def shiftManagement():
    if current_user.is_authenticated:
        # Get violation summary for dashboard
        from models import ShiftViolation
        violation_summary = ShiftViolation.get_violation_summary()
        return render_template('landing.html', violation_summary=violation_summary)
    return render_template('dashboard.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def shiftManagementLogin():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = bool(request.form.get('remember'))
        
        if not email or not password:
            flash('Please fill in all fields.', 'error')
            return render_template('login.html')
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password) and user.is_active:
            login_user(user, remember=remember)
            return redirect(url_for('auth.shiftManagement'))
        else:
            flash('Invalid email or password.', 'error')
    
    return render_template('login.html')

@auth_bp.route('/signup', methods=['GET', 'POST'])
def shiftManagementSignUp():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        role = request.form.get('role')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validation
        if not all([name, email, role, password, confirm_password]):
            flash('Please fill in all fields.', 'error')
            return render_template('signup.html')
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('signup.html')
        
        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
            return render_template('signup.html')
        
        # Check if user already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('An account with this email already exists.', 'error')
            return render_template('signup.html')
        
        # Create new user
        try:
            new_user = User(
                name=name,
                email=email,
                role=role,
                is_active=True
            )
            new_user.set_password(password)
            
            db.session.add(new_user)
            db.session.commit()
            
            flash('Account created successfully! Please log in.', 'success')
            return redirect(url_for('auth.shiftManagementLogin'))
            
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while creating your account. Please try again.', 'error')
    
    return render_template('signup.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.shiftManagement'))


@auth_bp.route("/api/login", methods=["POST"])
def api_login():
    """Login over REST API. Returns JSON instead of HTML."""
    data = request.get_json() or {}

    email = data.get("email", "").strip()
    password = data.get("password", "").strip()
    remember = bool(data.get("remember", False))

    if not email or not password:
        return jsonify({"ok": False, "message": "Please fill in all fields."}), 400

    user = User.query.filter_by(email=email).first()

    if not user or not user.check_password(password) or not user.is_active:
        return jsonify({"ok": False, "message": "Invalid email or password."}), 401

    login_user(user, remember=remember)

    return jsonify(
        {
            "ok": True,
            "message": "Login successful.",
            "redirect_url": url_for("auth.shiftManagement"),
        }
    ), 200


@auth_bp.route("/api/signup", methods=["POST"])
def api_signup():
    """Signup over REST API. Returns JSON instead of HTML."""
    data = request.get_json() or {}

    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    role = data.get("role", "").strip()
    password = data.get("password", "").strip()
    confirm_password = data.get("confirm_password", "").strip()

    if not name or not email or not role or not password or not confirm_password:
        return jsonify({"ok": False, "message": "Please fill in all fields."}), 400

    if password != confirm_password:
        return jsonify({"ok": False, "message": "Passwords do not match."}), 400

    existing = User.query.filter_by(email=email).first()
    if existing:
        return jsonify(
            {"ok": False, "message": "An account with this email already exists."}
        ), 400

    user = User(name=name, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    return jsonify(
        {
            "ok": True,
            "message": "Account created successfully.",
            "redirect_url": url_for("auth.shiftManagementLogin"),
        }
    ), 201
@auth_bp.route("/login/google")
def google_login():
    """
    Start Google OAuth login flow.
    Only works if GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET are configured and the
    provider has been registered in app.py.
    """
    oauth = current_app.extensions.get("authlib.integrations.flask_client")
    if oauth is None:
        flash("Google login is not configured.", "error")
        return redirect(url_for("auth.shiftManagementLogin"))

    google = oauth.create_client("google")
    if google is None:
        flash("Google login is not available.", "error")
        return redirect(url_for("auth.shiftManagementLogin"))

    redirect_uri = url_for("auth.google_authorize", _external=True)
    return google.authorize_redirect(redirect_uri)


def _infer_role_from_email(email: str) -> str:
    """
    Infer role from email address for Google logins:
    - If the local part (before @) contains any digit (e.g. class year like 26, 27),
      treat as a student.
    - Otherwise treat as a supervisor.
    """
    local_part = (email or "").split("@", 1)[0]
    return "student" if any(ch.isdigit() for ch in local_part) else "supervisor"


@auth_bp.route("/login/google/callback")
def google_authorize():
    """
    Google OAuth callback: finalize login and log in or create a user whose
    email matches the Google account email.

    Role assignment rule for Google logins:
    - Any email whose local part contains digits (e.g. 26, 27, or any number)
      is treated as a student.
    - Otherwise it is treated as a supervisor.
    """
    oauth = current_app.extensions.get("authlib.integrations.flask_client")
    if oauth is None:
        flash("Google login is not configured.", "error")
        return redirect(url_for("auth.shiftManagementLogin"))

    google = oauth.create_client("google")
    if google is None:
        flash("Google login is not available.", "error")
        return redirect(url_for("auth.shiftManagementLogin"))

    try:
        # Exchange code for tokens
        token = google.authorize_access_token()
    except Exception:
        current_app.logger.exception("Google OAuth authorize_access_token failed")
        flash("Google login failed. Please try again.", "error")
        return redirect(url_for("auth.shiftManagementLogin"))

    # Always use the official Google OpenID Connect userinfo endpoint.
    # This avoids needing to parse the ID token ourselves and sidesteps
    # library-specific nonce handling.
    user_info = None
    try:
        resp = google.get("https://openidconnect.googleapis.com/v1/userinfo")
        status = getattr(resp, "status_code", "n/a")
        current_app.logger.info("Google userinfo response status=%s", status)
        if resp.ok:
            user_info = resp.json()
        else:
            current_app.logger.warning(
                "Google userinfo request not ok: status=%s body=%s",
                status,
                getattr(resp, "text", "")[:200],
            )
    except Exception:
        current_app.logger.exception("Google userinfo request failed")
        user_info = None

    if not user_info:
        flash("Could not retrieve user information from Google.", "error")
        return redirect(url_for("auth.shiftManagementLogin"))

    email = user_info.get("email")
    if not email:
        flash("Your Google account does not have an email address.", "error")
        return redirect(url_for("auth.shiftManagementLogin"))

    # Find or create user based on email
    user = User.query.filter_by(email=email).first()

    if not user:
        # Infer role from email (digits -> student, else supervisor)
        role = _infer_role_from_email(email)

        # Best-effort name resolution from Google profile
        name = (
            user_info.get("name")
            or " ".join(
                part
                for part in [user_info.get("given_name"), user_info.get("family_name")]
                if part
            )
            or email.split("@", 1)[0]
        )

        # Generate a random password since Google is the auth source
        random_password = os.urandom(16).hex()

        user = User(
            name=name,
            email=email,
            role=role,
            is_active=True,
        )
        user.set_password(random_password)

        db.session.add(user)
        db.session.commit()

        flash(f"Account created from your Google login as {role}.", "success")

    if not user.is_active:
        flash("Your account is inactive. Please contact an administrator.", "error")
        return redirect(url_for("auth.shiftManagementLogin"))

    login_user(user, remember=True)
    flash("Logged in with Google.", "success")
    return redirect(url_for("auth.shiftManagement"))
