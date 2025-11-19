from flask import render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User
import os
import uuid
from dotenv import load_dotenv
from utils.recaptcha import verify_recaptcha

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
        recaptcha_response = request.form.get('g-recaptcha-response')
        
        if not email or not password:
            flash('Please fill in all fields.', 'error')
            return render_template('login.html')
        
        # Verify reCAPTCHA
        if not verify_recaptcha(recaptcha_response):
            flash('Please complete the reCAPTCHA verification.', 'error')
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
        recaptcha_response = request.form.get('g-recaptcha-response')
        
        # Validation
        if not all([name, email, role, password, confirm_password]):
            flash('Please fill in all fields.', 'error')
            return render_template('signup.html')
        
        # Verify reCAPTCHA
        if not verify_recaptcha(recaptcha_response):
            flash('Please complete the reCAPTCHA verification.', 'error')
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
    recaptcha_response = data.get("g-recaptcha-response", "").strip()

    if not email or not password:
        return jsonify({"ok": False, "message": "Please fill in all fields."}), 400

    # Verify reCAPTCHA
    if not verify_recaptcha(recaptcha_response):
        return jsonify({"ok": False, "message": "Please complete the reCAPTCHA verification."}), 400

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


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "").strip()

        if not all([name, email, password, role]):
            flash("All fields are required.", "error")
            return render_template("signup.html")

        if role not in ["student", "supervisor"]:
            flash("Invalid role selected.", "error")
            return render_template("signup.html")

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash("Email already registered. Please try logging in.", "error")
            return render_template("signup.html")

        # Create user
        user = User(name=name, email=email, role=role)
        user.set_password(password)
        user.is_active = True  # Activate immediately for now
        user.calendar_token = str(uuid.uuid4())

        db.session.add(user)
        db.session.commit()

        flash("Account created successfully! Please log in.", "success")
        return redirect(url_for("auth.shiftManagementLogin"))

    return render_template("signup.html")


# Google OAuth Routes
@auth_bp.route("/google/login")
def google_login():
    """Redirect user to Google OAuth."""
    from . import oauth
    if not oauth.google:
        flash("Google login is not configured.", "error")
        return redirect(url_for("auth.shiftManagementLogin"))

    # Generate a random nonce for security
    nonce = uuid.uuid4().hex
    redirect_uri = url_for("auth.google_authorized", _external=True)
    return oauth.google.authorize_redirect(redirect_uri, nonce=nonce)


@auth_bp.route("/google/authorized")
def google_authorized():
    """Handle Google OAuth callback."""
    from . import oauth
    if not oauth.google:
        flash("Google login is not configured.", "error")
        return redirect(url_for("auth.shiftManagementLogin"))

    try:
        token = oauth.google.authorize_access_token()
        user_info = token.get("userinfo")

        if not user_info:
            flash("Failed to get user information from Google.", "error")
            return redirect(url_for("auth.shiftManagementLogin"))

        email = user_info.get("email")
        name = user_info.get("name", "")

        if not email:
            flash("Google account must have a valid email address.", "error")
            return redirect(url_for("auth.shiftManagementLogin"))

        # Check if user exists
        user = User.query.filter_by(email=email).first()

        if not user:
            flash(
                "No account found for this email. Please sign up first or contact an administrator.",
                "error"
            )
            return redirect(url_for("auth.shiftManagementLogin"))

        # Update name if it's different
        if user.name != name and name:
            user.name = name
            db.session.commit()

    except Exception as e:
        current_app.logger.error(f"Google OAuth error: {e}")
        flash("Authentication failed. Please try again.", "error")
        return redirect(url_for("auth.shiftManagementLogin"))

    # Check if user account is active
    if not user.is_active:
        flash("Your account is inactive. Please contact an administrator.", "error")
        return redirect(url_for("auth.shiftManagementLogin"))

    login_user(user, remember=True)
    flash("Logged in with Google.", "success")
    return redirect(url_for("auth.shiftManagement"))


@auth_bp.route("/api/signup", methods=["POST"])
def api_signup():
    """Signup over REST API. Returns JSON instead of HTML."""
    data = request.get_json() or {}

    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    role = data.get("role", "").strip()
    password = data.get("password", "").strip()
    confirm_password = data.get("confirm_password", "").strip()
    recaptcha_response = data.get("g-recaptcha-response", "").strip()

    if not name or not email or not role or not password or not confirm_password:
        return jsonify({"ok": False, "message": "Please fill in all fields."}), 400

    # Verify reCAPTCHA
    if not verify_recaptcha(recaptcha_response):
        return jsonify({"ok": False, "message": "Please complete the reCAPTCHA verification."}), 400

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
