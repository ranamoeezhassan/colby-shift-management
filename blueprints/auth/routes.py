from flask import render_template, request, redirect, url_for, flash, jsonify
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
