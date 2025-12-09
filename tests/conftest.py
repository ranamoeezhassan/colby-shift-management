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
    app.config['SERVER_NAME'] = 'localhost'  # Needed for url_for in tests
    
    # Initialize database
    db.init_app(app)
    
    # Initialize login manager for route testing
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.shiftManagementLogin'  # Correct login route name
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # Register blueprints for route testing
    from blueprints.constraints import constraints_bp
    from blueprints.auth import auth_bp
    # Import routes to register them
    from blueprints.constraints import routes as constraints_routes
    from blueprints.auth import routes as auth_routes
    from blueprints.auth import init_google_oauth
    
    # Initialize Google OAuth (will log that it's not configured in test env)
    init_google_oauth(app)
    
    app.register_blueprint(constraints_bp)
    app.register_blueprint(auth_bp)
    
    # Register dummy blueprints for other app areas to prevent URL build errors
    from flask import Blueprint, render_template_string

    # Create dummy blueprints to satisfy base template navigation
    availability_bp = Blueprint('availability', __name__, url_prefix='/availability')
    staffing_bp = Blueprint('staffing', __name__, url_prefix='/staffing') 
    scheduler_bp = Blueprint('scheduler', __name__, url_prefix='/scheduler')
    outputs_bp = Blueprint('outputs', __name__, url_prefix='/outputs')
    ai_bp = Blueprint('ai', __name__, url_prefix='/ai', template_folder=os.path.join(project_root, 'blueprints/ai/templates'), static_folder=os.path.join(project_root, 'blueprints/ai/static'))

    @availability_bp.route('/')
    def index(): return "Availability Index"

    @staffing_bp.route('/')
    def index(): return "Staffing Index"

    @scheduler_bp.route('/')
    def index(): return "Scheduler Index"

    @outputs_bp.route('/')
    def index(): return "Outputs Index"

    @ai_bp.route('/ask_bar.html')
    def ask_bar():
        # Minimal dummy template for ask_bar.html
        return render_template_string('<div id="ai-bar">AI Bar</div>')

    app.register_blueprint(availability_bp)
    app.register_blueprint(staffing_bp)
    app.register_blueprint(scheduler_bp)
    app.register_blueprint(outputs_bp)
    app.register_blueprint(ai_bp)
    
    return app

@pytest.fixture
def client(app):
    """Create a test client"""
    return app.test_client()

@pytest.fixture(autouse=True)
def app_context(app):
    """Push app context for all tests"""
    with app.app_context():
        yield

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
def login(client):
    """Helper fixture to log in a user"""
    def _login(email, password):
        return client.post('/login', data={
            'email': email,
            'password': password,
            'g-recaptcha-response': 'test'
        }, follow_redirects=True)
    return _login

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