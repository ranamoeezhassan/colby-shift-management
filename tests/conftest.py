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
    from flask_login import LoginManager
    
    # Create Flask app for testing with proper template and static folders
    app = Flask(__name__, 
                template_folder=os.path.join(project_root, 'templates'),
                static_folder=os.path.join(project_root, 'static'))
    
    # Configure for testing
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'  # In-memory test database
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = 'test-secret-key'
    app.config['WTF_CSRF_ENABLED'] = False  # Disable CSRF for testing
    
    # Initialize database
    db.init_app(app)
    
    # Initialize login manager for route testing
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.shiftManagementLogin'  # Correct login route name
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # For staffing tests, we'll register minimal blueprints
    from flask import Blueprint, render_template_string
    
    # Create dummy blueprints to avoid import errors
    auth_bp = Blueprint('auth', __name__, url_prefix='/auth')
    availability_bp = Blueprint('availability', __name__, url_prefix='/availability')
    from blueprints.staffing import staffing_bp as real_staffing_bp

    @auth_bp.route('/shiftManagement')
    def shiftManagement():
        return "Shift Management"
    
    @auth_bp.route('/logout', endpoint='logout')
    def logout():
        return "Dummy logout route"

    # Restore dummy blueprints for other modules
    constraints_bp = Blueprint('constraints', __name__, url_prefix='/constraints')
    scheduler_bp = Blueprint('scheduler', __name__, url_prefix='/scheduler')
    outputs_bp = Blueprint('outputs', __name__, url_prefix='/outputs')
    @outputs_bp.route('/', endpoint='index')
    def outputs_index():
        return "Dummy outputs index"
    @outputs_bp.route('/index')
    def outputs_index_alias():
        return "Dummy outputs index alias"
    ai_bp = Blueprint('ai', __name__, url_prefix='/ai')

    app.register_blueprint(auth_bp)
    app.register_blueprint(availability_bp)
    app.register_blueprint(real_staffing_bp)
    app.register_blueprint(constraints_bp)
    app.register_blueprint(scheduler_bp)
    app.register_blueprint(outputs_bp)
    app.register_blueprint(ai_bp)
    
    with app.app_context():
        db.create_all()
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
def sample_user(app):
    """Create a sample user for testing"""
    with app.app_context():
        user = User(
            name="Test User",
            email="test@colby.edu",
            role="student",
            is_active=True
        )
        user.set_password("testpass")
        db.session.add(user)
        db.session.commit()
        # Return a fresh session-bound instance
        return User.query.filter_by(email="test@colby.edu").first()

@pytest.fixture
def sample_term(app):
    """Create a sample term for testing"""
    with app.app_context():
        term = Term(
            name="Fall 2025",
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
            availability_deadline=date(2025, 8, 15),
            locked=False
        )
        db.session.add(term)
        db.session.commit()
        # Return a fresh session-bound instance
        return Term.query.filter_by(name="Fall 2025").first()

@pytest.fixture
def mock_login(client, sample_user):
    """
    Mock login for tests needing authentication.
    Usage: mock_login('testuser')
    """
    def _login(username):
        with client.session_transaction() as sess:
            sess['_user_id'] = str(sample_user.user_id)
    return _login