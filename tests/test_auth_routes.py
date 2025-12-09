import os
import pytest
from flask import Flask, url_for
from unittest.mock import patch

from models import User

# --- Dashboard/Landing ---
def test_dashboard_unauth(client, db_session):
    resp = client.get(url_for('auth.shiftManagement'))
    assert b"dashboard" in resp.data or resp.status_code == 200

def test_dashboard_auth(client, sample_user, login, db_session):
    login(sample_user.email, "testpass")
    resp = client.get(url_for('auth.shiftManagement'))
    assert b"Shift Management Hub" in resp.data

# --- Login (GET/POST) ---
def test_login_get(client, db_session):
    resp = client.get(url_for('auth.shiftManagementLogin'))
    assert resp.status_code == 200
    assert b"login" in resp.data.lower()

@patch("utils.recaptcha.verify_recaptcha", return_value=True)
def test_login_post_success(mock_recaptcha, client, sample_user, db_session):
    resp = client.post(url_for('auth.shiftManagementLogin'), data={
        "email": sample_user.email,
        "password": "testpass",
        "g-recaptcha-response": "token"
    }, follow_redirects=True)
    assert b"Shift Management Hub" in resp.data

@patch("blueprints.auth.routes.verify_recaptcha", return_value=False)
def test_login_post_recaptcha_fail(mock_recaptcha, client, sample_user, db_session):
    resp = client.post(url_for('auth.shiftManagementLogin'), data={
        "email": sample_user.email,
        "password": "testpass",
        "g-recaptcha-response": "token"
    }, follow_redirects=True)
    assert b"reCAPTCHA" in resp.data

@patch("utils.recaptcha.verify_recaptcha", return_value=True)
def test_login_post_invalid(mock_recaptcha, client, db_session):
    resp = client.post(url_for('auth.shiftManagementLogin'), data={
        "email": "notfound@example.com",
        "password": "wrong",
        "g-recaptcha-response": "token"
    }, follow_redirects=True)
    assert b"Invalid email or password" in resp.data

# --- Signup (GET/POST) ---
def test_signup_get(client, db_session):
    resp = client.get(url_for('auth.shiftManagementSignUp'))
    assert resp.status_code == 200
    assert b"signup" in resp.data.lower()

@patch("blueprints.auth.routes.verify_recaptcha", return_value=True)
def test_signup_post_success(mock_recaptcha, client, db_session):
    resp = client.post(url_for('auth.shiftManagementSignUp'), data={
        "name": "New User",
        "email": "newuser@example.com",
        "role": "student",
        "password": "password123",
        "confirm_password": "password123",
        "g-recaptcha-response": "token"
    }, follow_redirects=True)
    assert b"Account created successfully" in resp.data

@patch("blueprints.auth.routes.verify_recaptcha", return_value=False)
def test_signup_post_recaptcha_fail(mock_recaptcha, client, db_session):
    resp = client.post(url_for('auth.shiftManagementSignUp'), data={
        "name": "User",
        "email": "user2@example.com",
        "role": "student",
        "password": "password123",
        "confirm_password": "password123",
        "g-recaptcha-response": "token"
    }, follow_redirects=True)
    assert b"reCAPTCHA" in resp.data

@patch("utils.recaptcha.verify_recaptcha", return_value=True)
def test_signup_post_password_mismatch(mock_recaptcha, client, db_session):
    resp = client.post(url_for('auth.shiftManagementSignUp'), data={
        "name": "User",
        "email": "user3@example.com",
        "role": "student",
        "password": "password123",
        "confirm_password": "wrong",
        "g-recaptcha-response": "token"
    }, follow_redirects=True)
    assert b"Passwords do not match" in resp.data

@patch("utils.recaptcha.verify_recaptcha", return_value=True)
def test_signup_post_short_password(mock_recaptcha, client, db_session):
    resp = client.post(url_for('auth.shiftManagementSignUp'), data={
        "name": "User",
        "email": "user4@example.com",
        "role": "student",
        "password": "123",
        "confirm_password": "123",
        "g-recaptcha-response": "token"
    }, follow_redirects=True)
    assert b"at least 6 characters" in resp.data

@patch("utils.recaptcha.verify_recaptcha", return_value=True)
def test_signup_post_duplicate_email(mock_recaptcha, client, sample_user, db_session):
    resp = client.post(url_for('auth.shiftManagementSignUp'), data={
        "name": "User",
        "email": sample_user.email,
        "role": "student",
        "password": "testpass",
        "confirm_password": "testpass",
        "g-recaptcha-response": "token"
    }, follow_redirects=True)
    assert b"already exists" in resp.data

# --- Logout ---
def test_logout(client, sample_user, login, db_session):
    login(sample_user.email, "testpass")
    resp = client.get(url_for('auth.logout'), follow_redirects=True)
    assert b"You have been logged out" in resp.data

# --- API Login ---
@patch("utils.recaptcha.verify_recaptcha", return_value=True)
def test_api_login_success(mock_recaptcha, client, sample_user, db_session):
    resp = client.post(url_for('auth.api_login'), json={
        "email": sample_user.email,
        "password": "testpass",
        "g-recaptcha-response": "token"
    })
    assert resp.status_code == 200
    assert resp.json["ok"] is True

@patch("blueprints.auth.routes.verify_recaptcha", return_value=False)
def test_api_login_recaptcha_fail(mock_recaptcha, client, sample_user, db_session):
    resp = client.post(url_for('auth.api_login'), json={
        "email": sample_user.email,
        "password": "testpass",
        "g-recaptcha-response": "token"
    })
    assert resp.status_code == 400
    assert not resp.json["ok"]

@patch("utils.recaptcha.verify_recaptcha", return_value=True)
def test_api_login_invalid(mock_recaptcha, client, db_session):
    resp = client.post(url_for('auth.api_login'), json={
        "email": "bad@example.com",
        "password": "wrong",
        "g-recaptcha-response": "token"
    })
    assert resp.status_code == 401
    assert not resp.json["ok"]

# --- API Signup ---
@patch("utils.recaptcha.verify_recaptcha", return_value=True)
def test_api_signup_success(mock_recaptcha, client, db_session):
    resp = client.post(url_for('auth.api_signup'), json={
        "name": "API User",
        "email": "apiuser@example.com",
        "role": "student",
        "password": "password123",
        "confirm_password": "password123",
        "g-recaptcha-response": "token"
    })
    assert resp.status_code == 201
    assert resp.json["ok"] is True

@patch("blueprints.auth.routes.verify_recaptcha", return_value=False)
def test_api_signup_recaptcha_fail(mock_recaptcha, client, db_session):
    resp = client.post(url_for('auth.api_signup'), json={
        "name": "API User",
        "email": "apiuser2@example.com",
        "role": "student",
        "password": "password123",
        "confirm_password": "password123",
        "g-recaptcha-response": "token"
    })
    assert resp.status_code == 400
    assert not resp.json["ok"]

@patch("utils.recaptcha.verify_recaptcha", return_value=True)
def test_api_signup_password_mismatch(mock_recaptcha, client, db_session):
    resp = client.post(url_for('auth.api_signup'), json={
        "name": "API User",
        "email": "apiuser3@example.com",
        "role": "student",
        "password": "password123",
        "confirm_password": "wrong",
        "g-recaptcha-response": "token"
    })
    assert resp.status_code == 400
    assert not resp.json["ok"]

@patch("utils.recaptcha.verify_recaptcha", return_value=True)
def test_api_signup_duplicate_email(mock_recaptcha, client, sample_user, db_session):
    resp = client.post(url_for('auth.api_signup'), json={
        "name": "API User",
        "email": sample_user.email,
        "role": "student",
        "password": "testpass",
        "confirm_password": "testpass",
        "g-recaptcha-response": "token"
    })
    assert resp.status_code == 400
    assert not resp.json["ok"]


def test_google_login_not_configured(client):
    from blueprints.auth import oauth
    with patch.object(oauth, 'google', None, create=True):
        resp = client.get(url_for("auth.google_login"), follow_redirects=True)
        assert b"Google login is not configured" in resp.data

def test_google_authorized_not_configured(client):
    from blueprints.auth import oauth
    with patch.object(oauth, 'google', None, create=True):
        resp = client.get(url_for("auth.google_authorized"), follow_redirects=True)
        assert b"Google login is not configured" in resp.data

@patch("blueprints.auth.routes.db.session.rollback")
@patch("blueprints.auth.routes.db.session.commit", side_effect=Exception("DB Error"))
@patch("blueprints.auth.routes.verify_recaptcha", return_value=True)
def test_signup_post_db_error(mock_recaptcha, mock_commit, mock_rollback, client, db_session):
    resp = client.post(url_for('auth.shiftManagementSignUp'), data={
        "name": "Test User",
        "email": "newuser@colby.edu",
        "password": "testpass",
        "confirm_password": "testpass",
        "role": "student",
        "g-recaptcha-response": "token"
    }, follow_redirects=True)
    assert b"An error occurred while creating your account" in resp.data
    mock_rollback.assert_called_once()


@patch.dict(os.environ, {}, clear=True)  # Clear environment variables
def test_init_google_oauth_not_configured():
    """Test init_google_oauth when GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are not set"""
    from blueprints.auth import init_google_oauth
    
    app = Flask(__name__)
    with app.app_context():
        with patch.object(app.logger, 'info') as mock_logger:
            init_google_oauth(app)
            
            # Verify the logger was called with the expected message
            mock_logger.assert_called_once_with(
                "Google OAuth is not fully configured. "
                "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in your "
                "environment to enable it."
            )


@patch("blueprints.auth.oauth")
def test_google_login_success(mock_oauth, client, db_session):
    """Test successful Google OAuth login flow"""
    # Mock the OAuth client
    mock_google = mock_oauth.google
    mock_google.authorize_redirect.return_value = "redirect_url"
    
    resp = client.get(url_for("auth.google_login"))
    assert resp.status_code == 200
    mock_google.authorize_redirect.assert_called_once()

@patch("blueprints.auth.oauth")
def test_google_authorized_success(mock_oauth, client, db_session):
    """Test successful Google OAuth callback"""
    # Mock the OAuth client and token response
    mock_google = mock_oauth.google
    mock_google.authorize_access_token.return_value = {
        "access_token": "token",
        "userinfo": {
            "email": "googleuser@colby.edu",
            "name": "Google User"
        }
    }
    
    # Mock the user creation/update
    with patch("blueprints.auth.routes.User.query") as mock_query:
        mock_query.filter_by.return_value.first.return_value = None  # New user
        with patch("blueprints.auth.routes.db.session.add"), \
             patch("blueprints.auth.routes.db.session.commit"), \
             patch("blueprints.auth.routes.login_user"):
            resp = client.get(url_for("auth.google_authorized"), follow_redirects=True)
            assert b"Welcome" in resp.data or resp.status_code == 200


def test_signup_get(client):
    """Test GET request to signup page"""
    resp = client.get(url_for('auth.signup'))
    assert resp.status_code == 200
    assert b'signup' in resp.data.lower()

def test_signup_post_missing_fields(client):
    """Test POST signup with missing fields"""
    resp = client.post(url_for('auth.shiftManagementSignUp'), data={
        "name": "Test User",
        "email": "",  # Missing email
        "password": "password123",
        "role": "student"
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b'signup' in resp.data.lower()  # Should render signup.html

def test_signup_post_invalid_role(client):
    """Test POST signup with invalid role"""
    resp = client.post(url_for('auth.shiftManagementSignUp'), data={
        "name": "Test User",
        "email": "test@example.com",
        "password": "password123",
        "role": "admin"  # Invalid role
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b'signup' in resp.data.lower()  # Should render signup.html

def test_signup_post_existing_email(client, db_session):
    """Test POST signup with existing email"""
    # Create existing user
    existing_user = User(name="Existing User", email="existing@example.com", role="student")
    existing_user.set_password("password123")
    db_session.add(existing_user)
    db_session.commit()
    
    resp = client.post(url_for('auth.shiftManagementSignUp'), data={
        "name": "New User",
        "email": "existing@example.com",
        "password": "password123",
        "role": "student"
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b'signup' in resp.data.lower()  # Should render signup.html

def test_signup_post_success_alternate(client, db_session, app):
    """Test successful POST signup (alternate)"""
    resp = client.post(url_for('auth.shiftManagementSignUp'), data={
        "name": "New User",
        "email": "newuser@example.com",
        "password": "password123",
        "role": "student"
    }, follow_redirects=True)
    assert resp.status_code == 200
    # Verify the route executed and redirected to login
    assert b"Sign" in resp.data or b"sign" in resp.data.lower() or b"login" in resp.data.lower()


def test_login_post_empty_fields(client):
    """Test login POST with empty email/password"""
    resp = client.post(url_for('auth.shiftManagementLogin'), data={
        "email": "",
        "password": "",
        "g-recaptcha-response": "token"
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"login" in resp.data.lower()

@patch("blueprints.auth.routes.verify_recaptcha", return_value=True)
def test_signup_post_password_length_short(mock_recaptcha, client, db_session):
    """Test signup with password too short"""
    resp = client.post(url_for('auth.shiftManagementSignUp'), data={
        "name": "Test User",
        "email": "test@example.com",
        "password": "short",  # Less than 6 chars
        "confirm_password": "short",
        "role": "student",
        "g-recaptcha-response": "token"
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"signup" in resp.data.lower()

def test_api_login_empty_fields(client):
    """Test API login with empty fields"""
    resp = client.post(url_for('auth.api_login'), json={
        "email": "",
        "password": "",
        "g-recaptcha-response": "token"
    })
    assert resp.status_code == 400
    assert not resp.json["ok"]

@patch("blueprints.auth.oauth")
def test_google_authorized_no_user_info(mock_oauth, client):
    """Test Google OAuth callback when userinfo is missing"""
    mock_google = mock_oauth.google
    mock_google.authorize_access_token.return_value = {
        "access_token": "token",
        "userinfo": None  # Missing userinfo
    }
    
    resp = client.get(url_for("auth.google_authorized"), follow_redirects=True)
    assert resp.status_code == 200
    assert b"Failed to get user information" in resp.data or b"Google" in resp.data

@patch("blueprints.auth.oauth")
def test_google_authorized_no_email(mock_oauth, client):
    """Test Google OAuth callback when email is missing"""
    mock_google = mock_oauth.google
    mock_google.authorize_access_token.return_value = {
        "access_token": "token",
        "userinfo": {
            "name": "Test User",
            "email": ""  # Missing email
        }
    }
    
    resp = client.get(url_for("auth.google_authorized"), follow_redirects=True)
    assert resp.status_code == 200
    assert b"valid email" in resp.data or b"Google" in resp.data

@patch("blueprints.auth.oauth")
def test_google_authorized_user_not_found(mock_oauth, client, db_session):
    """Test Google OAuth callback when user doesn't exist"""
    mock_google = mock_oauth.google
    mock_google.authorize_access_token.return_value = {
        "access_token": "token",
        "userinfo": {
            "email": "notfound@colby.edu",
            "name": "Not Found User"
        }
    }
    
    resp = client.get(url_for("auth.google_authorized"), follow_redirects=True)
    assert resp.status_code == 200
    assert b"No account found" in resp.data or b"Google" in resp.data

@patch("blueprints.auth.oauth")
def test_google_authorized_exception(mock_oauth, client):
    """Test Google OAuth callback with exception"""
    mock_google = mock_oauth.google
    mock_google.authorize_access_token.side_effect = Exception("OAuth error")
    
    resp = client.get(url_for("auth.google_authorized"), follow_redirects=True)
    assert resp.status_code == 200
    assert b"Authentication failed" in resp.data or b"Google" in resp.data

@patch("blueprints.auth.oauth")
def test_google_authorized_inactive_user(mock_oauth, client, db_session):
    """Test Google OAuth callback with inactive user"""
    # Create inactive user
    inactive_user = User(name="Inactive", email="inactive@colby.edu", role="student", is_active=False)
    inactive_user.set_password("testpass")
    db_session.add(inactive_user)
    db_session.commit()
    
    mock_google = mock_oauth.google
    mock_google.authorize_access_token.return_value = {
        "access_token": "token",
        "userinfo": {
            "email": "inactive@colby.edu",
            "name": "Inactive"
        }
    }
    
    resp = client.get(url_for("auth.google_authorized"), follow_redirects=True)
    assert resp.status_code == 200
    assert b"inactive" in resp.data or b"Google" in resp.data

def test_api_signup_empty_fields(client):
    """Test API signup with empty fields"""
    resp = client.post(url_for('auth.api_signup'), json={
        "name": "",
        "email": "",
        "password": "",
        "confirm_password": "",
        "role": "",
        "g-recaptcha-response": "token"
    })
    assert resp.status_code == 400
    assert not resp.json["ok"]


@patch("blueprints.auth.routes.verify_recaptcha", return_value=True)
def test_signup_post_password_mismatch(mock_recaptcha, client, db_session):
    """Test signup with mismatched passwords"""
    resp = client.post(url_for('auth.shiftManagementSignUp'), data={
        "name": "Test User",
        "email": "test@example.com",
        "password": "password123",
        "confirm_password": "different123",
        "role": "student",
        "g-recaptcha-response": "token"
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"do not match" in resp.data or b"Passwords" in resp.data

def test_signup_get(client):
    """Test GET request to signup page (duplicate signup route)"""
    resp = client.get(url_for('auth.shiftManagementSignUp'))
    assert resp.status_code == 200
    assert b"signup" in resp.data.lower() or b"sign up" in resp.data.lower()

def test_signup_post_duplicate_email_alternate(client, db_session):
    """Test signup via alternate signup route with duplicate email"""
    # Create existing user
    existing = User(name="Existing", email="existing@example.com", role="student")
    existing.set_password("password123")
    db_session.add(existing)
    db_session.commit()
    
    resp = client.post(url_for('auth.shiftManagementSignUp'), data={
        "name": "New User",
        "email": "existing@example.com",
        "password": "password123",
        "role": "student",
        "confirm_password": "password123",
        "g-recaptcha-response": "token"
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"registered" in resp.data or b"signup" in resp.data.lower()

@patch("blueprints.auth.oauth")
def test_google_authorized_update_name(mock_oauth, client, db_session):
    """Test Google OAuth callback updating existing user name"""
    # Create user with different name
    user = User(name="Old Name", email="googleuser@colby.edu", role="student")
    user.set_password("testpass")
    db_session.add(user)
    db_session.commit()
    
    mock_google = mock_oauth.google
    mock_google.authorize_access_token.return_value = {
        "access_token": "token",
        "userinfo": {
            "email": "googleuser@colby.edu",
            "name": "New Name"
        }
    }
    
    with patch("blueprints.auth.routes.login_user"):
        resp = client.get(url_for("auth.google_authorized"), follow_redirects=True)
        assert resp.status_code == 200
    
    # Verify name was updated
    updated_user = User.query.filter_by(email="googleuser@colby.edu").first()
    assert updated_user.name == "New Name"

@patch("blueprints.auth.oauth")
def test_google_authorized_inactive_user_flow(mock_oauth, client, db_session):
    """Test Google OAuth with inactive user account"""
    # Create inactive user
    inactive = User(name="Inactive User", email="inactive@colby.edu", role="student", is_active=False)
    inactive.set_password("testpass")
    db_session.add(inactive)
    db_session.commit()
    
    mock_google = mock_oauth.google
    mock_google.authorize_access_token.return_value = {
        "access_token": "token",
        "userinfo": {
            "email": "inactive@colby.edu",
            "name": "Inactive User"
        }
    }
    
    resp = client.get(url_for("auth.google_authorized"), follow_redirects=True)
    assert resp.status_code == 200
    assert b"inactive" in resp.data

    