from flask import Flask
from flask_login import LoginManager
from flask import request
from flask_cors import CORS
import os
from dotenv import load_dotenv

# Import database instance only - models will be imported later after app config
from models import db

# Import blueprint instances and auth initialization helpers (routes imported later)
from blueprints.auth import auth_bp, init_google_oauth
from blueprints.availability import availability_bp  
from blueprints.staffing import staffing_bp
from blueprints.constraints import constraints_bp
from blueprints.scheduler import scheduler_bp
from blueprints.outputs import outputs_bp

# Load environment variables (for SECRET_KEY, DATABASE_URL, GOOGLE_CLIENT_ID, etc.)
load_dotenv()

app = Flask(__name__)

# Configuration for Heroku
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Enable CORS for API endpoints
CORS(app)

# Database configuration - handle both local and Heroku environments
if os.environ.get('DATABASE_URL') or os.environ.get('JAWSDB_URL'):
    # Production (Heroku with JawsDB MySQL)
    database_url = os.environ.get('DATABASE_URL') or os.environ.get('JAWSDB_URL')
    
    # Handle postgres:// URLs from Heroku
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    # JawsDB provides mysql:// URLs, but we need to use PyMySQL driver
    elif database_url.startswith('mysql://'):
        database_url = database_url.replace('mysql://', 'mysql+pymysql://', 1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    print(f"Using production database: {database_url.split('@')[1] if '@' in database_url else 'production'}")
else:
    # Development - use SQLite
    basedir = os.path.abspath(os.path.dirname(__file__))
    instance_dir = os.path.join(basedir, 'instance')
    os.makedirs(instance_dir, exist_ok=True)
    db_path = os.path.join(instance_dir, 'shift_management.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    print(f"Using SQLite database: {db_path}")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.shiftManagementLogin'
login_manager.login_message = 'Please log in to access this page.'

# Configure Google OAuth (optional; only active if env vars are set).
# The actual configuration lives in the auth blueprint package so that
# auth-related logic stays together.
init_google_oauth(app)

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return db.session.get(User, int(user_id))

# Import routes after app configuration to avoid circular imports
from blueprints.auth import routes as auth_routes
from blueprints.availability import routes as availability_routes
from blueprints.staffing import routes as staffing_routes
from blueprints.constraints import routes as constraints_routes
from blueprints.scheduler import routes as scheduler_routes
from blueprints.outputs import routes as outputs_routes

# Register blueprints for routes
app.register_blueprint(auth_bp)
app.register_blueprint(availability_bp)
app.register_blueprint(staffing_bp)
app.register_blueprint(constraints_bp)
app.register_blueprint(scheduler_bp)
app.register_blueprint(outputs_bp)

# Simple health check for monitoring
@app.route('/health')
def health_check():
    return {'status': 'healthy'}, 200

# Only add debug instrumentation in development
if not os.environ.get('DATABASE_URL') and os.environ.get('FLASK_ENV') != 'production':
    @app.before_request
    def _debug_before_request():
        from flask_login import current_user
        print(f"TRACE: BEFORE {request.method} {request.path} is_authenticated={getattr(current_user, 'is_authenticated', None)}", flush=True)

    @app.after_request
    def _debug_after_request(resp):
        print(f"TRACE: AFTER  {request.method} {request.path} -> {resp.status_code} redirect_to={resp.headers.get('Location')}", flush=True)
        return resp
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    @event.listens_for(Session, "after_flush")
    def _after_flush(session, ctx):
        if session.new:
            print("TRACE: after_flush NEW objects:", [repr(o) for o in session.new], flush=True)

    @event.listens_for(Session, "after_commit")
    def _after_commit(session):
        print("TRACE: after_commit committed successfully", flush=True)

# Import all models so SQLAlchemy can create all tables
from models import User, Term, StaffingNeeds, Availability, Shift, Policy, UndesirableTimeWindow

# Create database tables
with app.app_context():
    try:
        db.create_all()
        print("Database tables created successfully!")
    except Exception as e:
        print(f"Error creating database tables: {e}")

if __name__ == '__main__':
    if os.environ.get('DATABASE_URL') or os.environ.get('JAWSDB_URL'):
        # Production - Heroku sets PORT environment variable
        port = int(os.environ.get('PORT', 5000))
        app.run(host='0.0.0.0', port=port)
    else:
        # Development - run on localhost:5000
        app.run(debug=True, host='127.0.0.1', port=5000)