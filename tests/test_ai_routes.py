import os
from types import SimpleNamespace

import pytest
from flask import Blueprint, Flask
from flask_login import LoginManager

from blueprints.ai import ai_bp, routes
from models import User, db

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def app():
    """Lightweight Flask app tailored for AI blueprint testing."""
    application = Flask(
        __name__,
        template_folder=os.path.join(PROJECT_ROOT, "templates"),
        static_folder=os.path.join(PROJECT_ROOT, "static"),
    )
    application.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SECRET_KEY="test-secret-key",
        WTF_CSRF_ENABLED=False,
    )

    db.init_app(application)

    login_manager = LoginManager()
    login_manager.init_app(application)

    @login_manager.user_loader
    def load_user(user_id):  # pragma: no cover - simple data fetch
        return db.session.get(User, int(user_id))

    auth_bp = Blueprint("auth", __name__)

    @auth_bp.route("/")
    def shiftManagement():  # pragma: no cover - trivial route
        return "Auth dashboard"

    application.register_blueprint(auth_bp)

    # Minimal blueprints for other sections referenced in AI routes.
    for name in ("availability", "staffing", "scheduler", "outputs", "constraints"):
        bp = Blueprint(name, __name__, url_prefix=f"/{name}")

        @bp.route("/")  # pragma: no cover - trivial route
        def index(name=name):
            return f"{name.title()} Index"

        application.register_blueprint(bp)

    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db_session(app):
    with app.app_context():
        db.create_all()
        yield db.session
        db.session.remove()
        db.drop_all()


@pytest.fixture
def sample_user(db_session):
    user = User(
        name="Sample User",
        email="sample@example.com",
        role="student",
        is_active=True,
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()
    return user


def _register_ai_dependencies(app):
    """Ensure the AI blueprint and all dependent endpoints exist for tests."""
    if "ai" not in app.blueprints:
        app.register_blueprint(ai_bp)

    def _dummy_view(*args, **kwargs):  # pragma: no cover - trivial helper
        return "OK"

    rule_map = [
        ("/availability/page", "availability.availability_page"),
        ("/outputs/student/<int:user_id>", "outputs.student_view"),
        ("/outputs/public/<token>", "outputs.public_schedule_view"),
        ("/outputs/all", "outputs.all_students_view"),
        ("/outputs/preview", "outputs.preview"),
    ]

    for rule, endpoint in rule_map:
        if not app.view_functions.get(endpoint):
            app.add_url_rule(rule, endpoint=endpoint, view_func=_dummy_view)


@pytest.fixture(autouse=True)
def clear_page_cache():
    routes._PAGE_TEXT_CACHE.clear()
    yield
    routes._PAGE_TEXT_CACHE.clear()


def _login(client, user):
    with client.session_transaction() as session:
        session["_user_id"] = str(user.user_id)
        session["_fresh"] = True


def _create_user(db_session, role="student", calendar_token=None, email_suffix="user"):
    user = User(
        name=f"{role.title()} User",
        email=f"{role}-{email_suffix}@example.com",
        role=role,
        is_active=True,
    )
    user.set_password("password123")
    if calendar_token:
        user.calendar_token = calendar_token
    db_session.add(user)
    db_session.commit()
    return user


def test_load_page_text_strips_tags_truncates_and_caches(app, tmp_path):
    _register_ai_dependencies(app)
    relative_dir = "tmp_ai_pages"
    relative_path = os.path.join(relative_dir, "page.html")
    full_dir = os.path.join(app.root_path, relative_dir)
    os.makedirs(full_dir, exist_ok=True)
    full_path = os.path.join(full_dir, "page.html")

    filler = "ABC" * 600
    noisy_html = f"""
        <html>
          <head>
            <style>.hidden {{ display:none; }}</style>
            <script>window.bad()</script>
          </head>
          <body>
            <div>{filler}</div>
          </body>
        </html>
    """

    with open(full_path, "w", encoding="utf-8") as f:
        f.write(noisy_html)

    with app.app_context():
        text = routes._load_page_text(relative_path)
        assert "<" not in text
        assert "window.bad()" not in text
        assert text.endswith(" ...")

        os.remove(full_path)
        cached = routes._load_page_text(relative_path)
        assert cached == text  # Served from cache despite missing file now.


def test_load_page_text_missing_file_returns_empty(app):
    _register_ai_dependencies(app)
    with app.app_context():
        assert routes._load_page_text("does/not/exist.html") == ""


def test_build_routes_for_student_includes_personal_links(app, monkeypatch):
    _register_ai_dependencies(app)
    with app.test_request_context():
        dummy_user = SimpleNamespace(user_id=17, calendar_token="tok-123")
        monkeypatch.setattr(routes, "current_user", dummy_user, raising=False)

        result = routes._build_routes_for_role("student")

        assert "student_schedule" in result
        assert result["student_schedule"].endswith("/17")
        assert "public_schedule" in result
        assert result["public_schedule"].endswith("/tok-123")


def test_build_routes_for_student_catches_url_errors(app, monkeypatch):
    _register_ai_dependencies(app)
    with app.test_request_context():
        # Setup current_user
        dummy_user = SimpleNamespace(user_id=17, calendar_token="tok-123")
        monkeypatch.setattr(routes, "current_user", dummy_user, raising=False)

        original_url_for = routes.url_for

        def flaky_url_for(endpoint, **values):
            if endpoint == "outputs.student_view":
                raise ValueError("Student view url fail")
            if endpoint == "outputs.public_schedule_view":
                raise ValueError("Public view url fail")
            return original_url_for(endpoint, **values)

        monkeypatch.setattr(routes, "url_for", flaky_url_for)

        # Should not raise exception
        result = routes._build_routes_for_role("student")
        
        # Base routes should still be there
        assert "dashboard" in result
        assert "outputs_index" in result
        # Failed routes should be missing
        assert "student_schedule" not in result
        assert "public_schedule" not in result



def test_build_routes_for_supervisor_survives_url_errors(app, monkeypatch):
    _register_ai_dependencies(app)
    with app.test_request_context():
        original_url_for = routes.url_for

        def flaky_url_for(endpoint, **values):
            supervisor_endpoints = (
                "availability.",
                "staffing.",
                "constraints.",
                "scheduler.",
            )
            optional_outputs = {
                "outputs.student_view",
                "outputs.public_schedule_view",
                "outputs.all_students_view",
                "outputs.preview",
            }
            if endpoint.startswith(supervisor_endpoints) or endpoint in optional_outputs:
                raise RuntimeError("boom")
            return original_url_for(endpoint, **values)

        monkeypatch.setattr(routes, "url_for", flaky_url_for)

        result = routes._build_routes_for_role("supervisor")

        assert result["dashboard"] == original_url_for("auth.shiftManagement")
        assert result["outputs_index"] == original_url_for("outputs.index")
        # Optional supervisor routes are skipped when URL building fails.
        assert "availability_page" not in result
        assert "all_students_view" not in result


def test_ai_query_requires_question(app, db_session, sample_user):
    _register_ai_dependencies(app)
    client = app.test_client()
    _login(client, sample_user)

    response = client.post("/api/ai/query", json={"question": "   "})
    assert response.status_code == 400
    assert response.get_json()["error"] == "Question is required."


def test_ai_query_returns_answer_with_descriptions(app, db_session, monkeypatch):
    _register_ai_dependencies(app)
    client = app.test_client()
    user = _create_user(db_session, role="student", calendar_token="cal-1", email_suffix="desc")
    _login(client, user)

    captured = {}

    def fake_get_nav(question, context):
        captured["question"] = question
        captured["context"] = context
        return "Mock answer"

    monkeypatch.setattr(routes, "get_navigation_help", fake_get_nav)

    response = client.post("/api/ai/query", json={"question": " Where do I view my schedule? "})

    assert response.status_code == 200
    assert response.get_json() == {"answer": "Mock answer"}
    assert captured["question"] == "Where do I view my schedule?"
    assert captured["context"]["routes"]["student_schedule"].endswith(str(user.user_id))
    assert captured["context"]["pages"]["dashboard"].startswith("Student dashboard")


def test_ai_query_falls_back_to_html_snapshot(app, db_session, monkeypatch):
    _register_ai_dependencies(app)
    client = app.test_client()
    user = _create_user(db_session, role="student", email_suffix="html")
    _login(client, user)

    original_student_desc = routes.ROLE_PAGE_DESCRIPTIONS["student"]
    monkeypatch.setitem(routes.ROLE_PAGE_DESCRIPTIONS, "student", {})

    # Provide simple HTML files so _load_page_text has real content to read.
    html_targets = {
        "blueprints/auth/templates/landing.html": "<h1>Dashboard</h1>",
        "blueprints/outputs/templates/outputs_index.html": "<p>Outputs</p>",
    }
    for rel_path, body in html_targets.items():
        full_path = os.path.join(app.root_path, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as handle:
            handle.write(body)

    captured = {}

    def fake_get_nav(question, context):
        captured["pages"] = context["pages"]
        return "ok"

    monkeypatch.setattr(routes, "get_navigation_help", fake_get_nav)

    response = client.post("/api/ai/query", json={"question": "help"})

    assert response.status_code == 200
    assert captured["pages"]["dashboard"]  # Snapshot text retrieved from HTML
    assert captured["pages"]["outputs_index"]

    # Restore descriptions for other tests.
    routes.ROLE_PAGE_DESCRIPTIONS["student"] = original_student_desc


def test_ai_query_handles_runtime_error(app, db_session, sample_user, monkeypatch):
    _register_ai_dependencies(app)
    client = app.test_client()
    _login(client, sample_user)

    def broken_get_nav(question, context):
        raise RuntimeError("Missing GROQ key")

    monkeypatch.setattr(routes, "get_navigation_help", broken_get_nav)

    response = client.post("/api/ai/query", json={"question": "Anything"})

    assert response.status_code == 500
    assert response.get_json()["error"] == "Missing GROQ key"


def test_ai_query_handles_generic_error(app, db_session, sample_user, monkeypatch):
    _register_ai_dependencies(app)
    client = app.test_client()
    _login(client, sample_user)

    def generic_failure(question, context):
        raise ValueError("boom")

    monkeypatch.setattr(routes, "get_navigation_help", generic_failure)

    response = client.post("/api/ai/query", json={"question": "Anything"})

    assert response.status_code == 500
    assert response.get_json()["error"] == "Assistant is temporarily unavailable."

