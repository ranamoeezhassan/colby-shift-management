import sys
import os
import pytest
from datetime import datetime, date, time

# Add the project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Now we can import from the project
from models import db, User, Term, Availability, StaffingNeeds

@pytest.fixture
def app():
    """Create and configure a test app"""
    from flask import Flask
    
    # Create Flask app for testing
    app = Flask(__name__)
    
    # Configure for testing
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'  # In-memory test database
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = 'test-secret-key'
    app.config['WTF_CSRF_ENABLED'] = False  # Disable CSRF for testing
    
    # Initialize database
    db.init_app(app)
    
    return app

@pytest.fixture
def client(app):
    """Create a test client"""
    return app.test_client()

@pytest.fixture
def runner(app):
    """Create a test CLI runner"""
    return app.test_cli_runner()

@pytest.fixture
def db_session(app):
    """Create a database session for testing"""
    with app.app_context():
        # Create all tables fresh for each test
        db.create_all()
        
        yield db.session
        
        # Clean up after each test
        db.session.remove()
        db.drop_all()

@pytest.fixture
def sample_user(db_session):
    """Create a sample user for testing"""
    user = User(
        name="Test User",
        email="test@colby.edu", 
        role="student",
        is_active=True
    )
    user.set_password("testpass")
    
    db_session.add(user)
    db_session.commit()
    
    return user

@pytest.fixture
def sample_term(db_session):
    """Create a sample term for testing"""
    term = Term(
        name="Fall 2025",
        start_date=date(2025, 9, 1),
        end_date=date(2025, 12, 15),
        availability_deadline=date(2025, 8, 15),
        locked=False
    )
    
    db_session.add(term)
    db_session.commit()
    
    return term