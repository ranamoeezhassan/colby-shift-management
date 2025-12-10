import io
import csv
from datetime import date, time

import pytest
from flask import Flask
from flask_login import LoginManager
from sqlalchemy.pool import StaticPool

from models import db, User, Term, Availability
from blueprints.availability import availability_bp
import blueprints.availability.routes as availability_routes


# -------------------------------------------------------------------
# FIXTURES
# -------------------------------------------------------------------

@pytest.fixture
def app():
    """
    GIVEN a Flask app configured for testing
    WHEN tests run
    THEN use a single shared in-memory SQLite DB with all tables created
    """
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        # Use "sqlite://" + StaticPool to share one in-memory DB
        SQLALCHEMY_DATABASE_URI="sqlite://",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        },
    )

    # Init DB
    db.init_app(app)

    # Flask-Login setup
    login_manager = LoginManager()
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        # Use db.session.get for SQLAlchemy 2.x style
        return db.session.get(User, int(user_id))

    # Register blueprint
    app.register_blueprint(availability_bp)

    # Create all tables for *this* app/engine
    with app.app_context():
        db.create_all()
        # Make sure SQLAlchemy does not expire objects on commit
        db.session.expire_on_commit = False

        # Everything that depends on `app` runs inside this app_context
        yield app

        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture
def client(app):
    """
    Simple Flask test client fixture.
    """
    return app.test_client()


@pytest.fixture
def supervisor_user(app):
    """
    GIVEN a supervisor user in the DB
    WHEN tests need a logged-in supervisor
    THEN this fixture supplies it

    NOTE: No extra app.app_context() here – we are already inside the
    app context provided by the `app` fixture.
    """
    user = User(
        name="Supervisor Sue",
        email="supervisor@example.com",
        role="supervisor",
        is_active=True,
        password_hash="x",
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def student_user(app):
    """
    GIVEN a student user in the DB
    WHEN tests need a logged-in student
    THEN this fixture supplies it
    """
    user = User(
        name="Student Sam",
        email="student@example.com",
        role="student",
        is_active=True,
        password_hash="x",
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def term(app):
    """
    GIVEN a term in the DB
    WHEN term-related endpoints are called
    THEN this fixture provides a real term
    """
    t = Term(
        name="Spring 2026",
        start_date=date(2026, 1, 10),
        end_date=date(2026, 5, 10),
        availability_deadline=date(2026, 1, 5),
        locked=False,
    )
    db.session.add(t)
    db.session.commit()
    return t


def login(client, user):
    """
    Helper: mark the given user as logged-in for this test client.
    Uses Flask-Login's session keys.
    """
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.user_id)
        sess["_fresh"] = True


# -------------------------------------------------------------------
# availability_page
# -------------------------------------------------------------------

def test_availability_page_renders(app, client, supervisor_user, monkeypatch):
    """
    GIVEN a logged-in supervisor
    WHEN GET /availability/page is requested
    THEN the route should render the availability_index.html template (200 OK)
    """
    login(client, supervisor_user)

    # Avoid needing a real template file: stub render_template
    monkeypatch.setattr(
        availability_routes,
        "render_template",
        lambda template_name: f"Rendered {template_name}",
    )

    resp = client.get("/availability/page")
    assert resp.status_code == 200
    assert b"Rendered availability_index.html" in resp.data


# -------------------------------------------------------------------
# get_terms
# -------------------------------------------------------------------

def test_get_terms_empty(app, client, supervisor_user):
    """
    GIVEN no terms in the database
    WHEN GET /availability/api/v1/terms is called
    THEN it should return an empty list with 200
    """
    login(client, supervisor_user)

    resp = client.get("/availability/api/v1/terms")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_get_terms_nonempty(app, client, supervisor_user, term):
    """
    GIVEN at least one term in the database
    WHEN GET /availability/api/v1/terms is called
    THEN it should return a list of term dicts with isoformat dates
    """
    login(client, supervisor_user)

    resp = client.get("/availability/api/v1/terms")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["term_id"] == term.term_id
    assert data[0]["name"] == term.name
    assert data[0]["start_date"] == term.start_date.isoformat()
    assert data[0]["end_date"] == term.end_date.isoformat()


# -------------------------------------------------------------------
# get_availability
# -------------------------------------------------------------------

def test_get_availability_missing_term_id(client, supervisor_user):
    """
    GIVEN a logged-in supervisor
    WHEN GET /availability/api/v1/availability is called without term_id
    THEN 400 and error message are returned
    """
    login(client, supervisor_user)

    resp = client.get("/availability/api/v1/availability")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "term_id is required"


def test_get_availability_term_not_found(client, supervisor_user):
    """
    GIVEN a logged-in supervisor
    WHEN GET /availability/api/v1/availability?term_id=999 is called
    THEN 404 and 'Term not found' are returned
    """
    login(client, supervisor_user)

    resp = client.get("/availability/api/v1/availability?term_id=999")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "Term not found"


def test_get_availability_supervisor_sees_all(app, client, supervisor_user, student_user, term):
    """
    GIVEN a supervisor, a student, and availability rows for both
    WHEN the supervisor calls GET /availability/api/v1/availability?term_id=<id>
    THEN the JSON includes availability for both users
    """
    login(client, supervisor_user)
    with app.app_context():
        a1 = Availability(
            user_id=supervisor_user.user_id,
            term_id=term.term_id,
            day_of_week="Mon",
            start_time=time(9, 0),
            end_time=time(11, 0),
        )
        a2 = Availability(
            user_id=student_user.user_id,
            term_id=term.term_id,
            day_of_week="Tue",
            start_time=time(10, 0),
            end_time=time(12, 0),
        )
        db.session.add_all([a1, a2])
        db.session.commit()

    resp = client.get(f"/availability/api/v1/availability?term_id={term.term_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    avail = data["availability"]
    # Both users appear
    assert "Supervisor Sue" in avail
    assert "Student Sam" in avail
    assert avail["Supervisor Sue"]["Mon"] == ["09:00-11:00"]
    assert avail["Student Sam"]["Tue"] == ["10:00-12:00"]


def test_get_availability_student_sees_self_only(app, client, student_user, supervisor_user, term):
    """
    GIVEN a student user and a supervisor, both with availability
    WHEN the student calls GET /availability/api/v1/availability?term_id=<id>
    THEN the JSON includes only that student's availability
    """
    login(client, student_user)
    with app.app_context():
        a1 = Availability(
            user_id=supervisor_user.user_id,
            term_id=term.term_id,
            day_of_week="Mon",
            start_time=time(9, 0),
            end_time=time(11, 0),
        )
        a2 = Availability(
            user_id=student_user.user_id,
            term_id=term.term_id,
            day_of_week="Tue",
            start_time=time(10, 0),
            end_time=time(12, 0),
        )
        db.session.add_all([a1, a2])
        db.session.commit()

    resp = client.get(f"/availability/api/v1/availability?term_id={term.term_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    avail = data["availability"]

    assert "Student Sam" in avail
    assert "Supervisor Sue" not in avail
    assert avail["Student Sam"]["Tue"] == ["10:00-12:00"]


# -------------------------------------------------------------------
# update_availability (POST JSON)
# -------------------------------------------------------------------

def test_update_availability_missing_term_id(client, supervisor_user):
    """
    GIVEN a logged-in supervisor
    WHEN POST /availability/api/v1/availability with no term_id
    THEN 400 with appropriate error is returned
    """
    login(client, supervisor_user)
    resp = client.post(
        "/availability/api/v1/availability",
        json={"rows": []},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "term_id is required"


def test_update_availability_term_not_found(client, supervisor_user):
    """
    GIVEN a logged-in supervisor
    WHEN POST /availability/api/v1/availability with unknown term_id
    THEN 404 'Term not found' is returned
    """
    login(client, supervisor_user)
    resp = client.post(
        "/availability/api/v1/availability",
        json={"term_id": 999, "rows": []},
    )
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "Term not found"


def test_update_availability_user_not_found(app, client, supervisor_user, term):
    """
    GIVEN a term and JSON rows referencing an unknown user
    WHEN POST /availability/api/v1/availability is called
    THEN 207 is returned and errors mention missing user
    """
    login(client, supervisor_user)

    resp = client.post(
        "/availability/api/v1/availability",
        json={
            "term_id": term.term_id,
            "rows": [
                {"student_name": "Ghost User", "Mon": "09:00-11:00"}
            ],
        },
    )
    assert resp.status_code == 207
    data = resp.get_json()
    assert "User 'Ghost User' not found" in data["errors"]


def test_update_availability_invalid_block_format(app, client, supervisor_user, term, student_user):
    """
    GIVEN a real user and term, but malformed block text without '-'
    WHEN POST /availability/api/v1/availability is called
    THEN 207 is returned and an error about invalid block is recorded
    """
    login(client, supervisor_user)

    resp = client.post(
        "/availability/api/v1/availability",
        json={
            "term_id": term.term_id,
            "rows": [
                {"student_name": student_user.name, "Mon": "0900"}  # no '-'
            ],
        },
    )
    assert resp.status_code == 207
    errors = resp.get_json()["errors"]
    assert any("Invalid block" in e for e in errors)


def test_update_availability_invalid_time_format(app, client, supervisor_user, term, student_user):
    """
    GIVEN a real user and term, but an invalid HH:MM time
    WHEN POST /availability/api/v1/availability is called
    THEN 207 is returned and error about invalid time format is recorded
    """
    login(client, supervisor_user)

    resp = client.post(
        "/availability/api/v1/availability",
        json={
            "term_id": term.term_id,
            "rows": [
                {"student_name": student_user.name, "Mon": "25:00-26:00"}
            ],
        },
    )
    assert resp.status_code == 207
    errors = resp.get_json()["errors"]
    assert any("Invalid time format" in e for e in errors)


def test_update_availability_single_block_success(app, client, supervisor_user, term, student_user):
    """
    GIVEN a real user and term
    WHEN POST /availability/api/v1/availability with one valid block per day
    THEN 200 is returned and DB contains matching Availability row
    """
    login(client, supervisor_user)

    resp = client.post(
        "/availability/api/v1/availability",
        json={
            "term_id": term.term_id,
            "rows": [
                {"student_name": student_user.name, "Mon": "09:00-11:00"}
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["message"] == "Availability updated"
    assert data["errors"] == []

    with app.app_context():
        rows = Availability.query.filter_by(
            user_id=student_user.user_id,
            term_id=term.term_id,
            day_of_week="Mon",
        ).all()
        assert len(rows) == 1
        assert rows[0].start_time == time(9, 0)
        assert rows[0].end_time == time(11, 0)


def test_update_availability_multiple_blocks_overwrites(app, client, supervisor_user, term, student_user):
    """
    GIVEN existing availability for a user/day
    WHEN POST /availability/api/v1/availability with multiple blocks for that day
    THEN old rows are removed and replaced with new ones matching all blocks
    """
    login(client, supervisor_user)
    with app.app_context():
        old = Availability(
            user_id=student_user.user_id,
            term_id=term.term_id,
            day_of_week="Mon",
            start_time=time(8, 0),
            end_time=time(9, 0),
        )
        db.session.add(old)
        db.session.commit()

    resp = client.post(
        "/availability/api/v1/availability",
        json={
            "term_id": term.term_id,
            "rows": [
                {"student_name": student_user.name, "Mon": "09:00-11:00, 13:00-15:00"}
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["errors"] == []

    with app.app_context():
        rows = Availability.query.filter_by(
            user_id=student_user.user_id,
            term_id=term.term_id,
            day_of_week="Mon",
        ).order_by(Availability.start_time).all()
        assert len(rows) == 2
        assert rows[0].start_time == time(9, 0)
        assert rows[0].end_time == time(11, 0)
        assert rows[1].start_time == time(13, 0)
        assert rows[1].end_time == time(15, 0)


def test_update_availability_ignores_blank_student_rows(app, client, supervisor_user, term, student_user):
    """
    GIVEN a payload that includes a row with blank student_name
    WHEN POST /availability/api/v1/availability is called
    THEN the blank row is ignored and no error is recorded
    """
    login(client, supervisor_user)

    resp = client.post(
        "/availability/api/v1/availability",
        json={
            "term_id": term.term_id,
            "rows": [
                {"student_name": "   ", "Mon": "09:00-11:00"},  # should be skipped
                {"student_name": student_user.name, "Mon": "10:00-12:00"},
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    # No errors; the blank row is silently ignored
    assert data["errors"] == []

    with app.app_context():
        rows = Availability.query.filter_by(
            user_id=student_user.user_id,
            term_id=term.term_id,
            day_of_week="Mon",
        ).all()
        assert len(rows) == 1
        assert rows[0].start_time == time(10, 0)
        assert rows[0].end_time == time(12, 0)


# -------------------------------------------------------------------
# upload_availability_csv
# -------------------------------------------------------------------

def _make_csv_file(rows):
    """
    Utility to build an in-memory CSV file-like object from a list of dicts.
    """
    output = io.StringIO()
    writer = csv.DictWriter(
        output, fieldnames=["name", "day_of_week", "start_time", "end_time"]
    )
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    output.seek(0)
    return output


def test_upload_csv_missing_term_id(client, supervisor_user):
    """
    GIVEN a logged-in supervisor
    WHEN POST /availability/api/v1/availability/upload without term_id
    THEN 400 and 'term_id is required' are returned
    """
    login(client, supervisor_user)
    resp = client.post("/availability/api/v1/availability/upload", data={})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "term_id is required"


def test_upload_csv_term_not_found(client, supervisor_user):
    """
    GIVEN a logged-in supervisor
    WHEN POST /availability/api/v1/availability/upload with unknown term_id
    THEN 404 'Term not found' is returned
    """
    login(client, supervisor_user)
    resp = client.post(
        "/availability/api/v1/availability/upload",
        data={"term_id": 999},
    )
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "Term not found"


def test_upload_csv_invalid_file(client, supervisor_user, term):
    """
    GIVEN a logged-in supervisor and term
    WHEN upload is called with no file or wrong extension
    THEN 400 'Please upload a valid CSV file' is returned
    """
    login(client, supervisor_user)
    resp = client.post(
        "/availability/api/v1/availability/upload",
        data={"term_id": term.term_id},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "Please upload a valid CSV file"


def test_upload_csv_partial_success(app, client, supervisor_user, term, student_user):
    """
    GIVEN a CSV where some rows are valid and one references a missing user
    WHEN POST /availability/api/v1/availability/upload is called
    THEN status 207, partial success summary, and row-level errors are returned
    """
    login(client, supervisor_user)

    csv_io = _make_csv_file([
        {
            "name": student_user.name,
            "day_of_week": "Monday",
            "start_time": "09:00",
            "end_time": "11:00",
        },
        {
            "name": "Unknown User",
            "day_of_week": "Tuesday",
            "start_time": "10:00",
            "end_time": "12:00",
        },
    ])

    data = {
        "term_id": str(term.term_id),
        "csv_file": (io.BytesIO(csv_io.read().encode("utf-8")), "test.csv"),
    }
    resp = client.post(
        "/availability/api/v1/availability/upload",
        data=data,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 207
    body = resp.get_json()
    assert body["summary"]["total_rows"] == 2
    assert body["summary"]["processed_rows"] == 1
    assert body["summary"]["error_rows"] == 1
    assert body["summary"]["partial_success"] is True
    assert any("user 'Unknown User' not found" in e for e in body["errors"])

    # DB contains only the good row
    with app.app_context():
        rows = Availability.query.filter_by(term_id=term.term_id).all()
        assert len(rows) == 1
        assert rows[0].user_id == student_user.user_id
        assert rows[0].day_of_week == "Mon"


def test_upload_csv_all_invalid(app, client, supervisor_user, term):
    """
    GIVEN a CSV where all rows are invalid (bad times)
    WHEN POST /availability/api/v1/availability/upload is called
    THEN 400 returned and no rows are imported
    """
    login(client, supervisor_user)

    csv_io = _make_csv_file([
        {
            "name": "Nobody",
            "day_of_week": "Monday",
            "start_time": "99:00",
            "end_time": "aa:bb",
        }
    ])

    data = {
        "term_id": str(term.term_id),
        "csv_file": (io.BytesIO(csv_io.read().encode("utf-8")), "bad.csv"),
    }
    resp = client.post(
        "/availability/api/v1/availability/upload",
        data=data,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert "no rows were imported" in body["message"]

    with app.app_context():
        rows = Availability.query.filter_by(term_id=term.term_id).all()
        assert rows == []


def test_upload_csv_all_valid(app, client, supervisor_user, term, student_user):
    """
    GIVEN a CSV where all rows are valid and match existing users
    WHEN POST /availability/api/v1/availability/upload is called
    THEN 200 returned and all rows imported
    """
    login(client, supervisor_user)

    csv_io = _make_csv_file([
        {
            "name": student_user.name,
            "day_of_week": "Monday",
            "start_time": "09:00",
            "end_time": "11:00",
        },
        {
            "name": student_user.name,
            "day_of_week": "Tuesday",
            "start_time": "13:00",
            "end_time": "15:00",
        },
    ])

    data = {
        "term_id": str(term.term_id),
        "csv_file": (io.BytesIO(csv_io.read().encode("utf-8")), "good.csv"),
    }
    resp = client.post(
        "/availability/api/v1/availability/upload",
        data=data,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["summary"]["total_rows"] == 2
    assert body["summary"]["processed_rows"] == 2
    assert body["summary"]["error_rows"] == 0

    with app.app_context():
        rows = Availability.query.filter_by(
            user_id=student_user.user_id,
            term_id=term.term_id,
        ).all()
        assert len(rows) == 2


def test_upload_csv_skips_blank_rows(app, client, supervisor_user, term, student_user):
    """
    GIVEN a CSV that contains a completely blank row
    WHEN POST /availability/api/v1/availability/upload is called
    THEN the blank row is skipped and not counted in total_rows
    """
    login(client, supervisor_user)

    csv_io = _make_csv_file([
        {
            "name": student_user.name,
            "day_of_week": "Monday",
            "start_time": "09:00",
            "end_time": "11:00",
        },
        # Completely blank row that should be ignored
        {"name": "", "day_of_week": "", "start_time": "", "end_time": ""},
    ])

    data = {
        "term_id": str(term.term_id),
        "csv_file": (io.BytesIO(csv_io.read().encode("utf-8")), "blank_row.csv"),
    }
    resp = client.post(
        "/availability/api/v1/availability/upload",
        data=data,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    body = resp.get_json()
    # Only the non-empty row should be counted
    assert body["summary"]["total_rows"] == 1
    assert body["summary"]["processed_rows"] == 1
    assert body["summary"]["error_rows"] == 0

    with app.app_context():
        rows = Availability.query.filter_by(term_id=term.term_id).all()
        assert len(rows) == 1


def test_upload_csv_unexpected_exception_returns_500(
    app, client, supervisor_user, term, student_user, monkeypatch
):
    """
    GIVEN a CSV upload where an unexpected error occurs inside the handler
    WHEN POST /availability/api/v1/availability/upload is called
    THEN the route returns 500 and an 'Error uploading CSV' message
    """
    login(client, supervisor_user)

    csv_io = _make_csv_file([
        {
            "name": student_user.name,
            "day_of_week": "Monday",
            "start_time": "09:00",
            "end_time": "11:00",
        }
    ])

    data = {
        "term_id": str(term.term_id),
        "csv_file": (io.BytesIO(csv_io.read().encode("utf-8")), "boom.csv"),
    }

    # Force an exception inside the try-block by monkeypatching io.StringIO
    class BoomIO:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(availability_routes.io, "StringIO", BoomIO)

    resp = client.post(
        "/availability/api/v1/availability/upload",
        data=data,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 500
    body = resp.get_json()
    assert "Error uploading CSV" in body["error"]


# -------------------------------------------------------------------
# export_availability_csv
# -------------------------------------------------------------------

def test_export_availability_missing_term_id(client, supervisor_user):
    """
    GIVEN a logged-in supervisor
    WHEN GET /availability/api/v1/availability/export with no term_id
    THEN 400 'term_id is required' is returned
    """
    login(client, supervisor_user)
    resp = client.get("/availability/api/v1/availability/export")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "term_id is required"


def test_export_availability_term_not_found(client, supervisor_user):
    """
    GIVEN a logged-in supervisor
    WHEN GET /availability/api/v1/availability/export?term_id=999
    THEN 404 'Term not found' is returned
    """
    login(client, supervisor_user)
    resp = client.get("/availability/api/v1/availability/export?term_id=999")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "Term not found"


def test_export_availability_success_supervisor(app, client, supervisor_user, term, student_user):
    """
    GIVEN availability rows in the DB
    WHEN GET /availability/api/v1/availability/export?term_id=<id> is called by a supervisor
    THEN a CSV file is returned containing matching rows for all users
    """
    login(client, supervisor_user)

    with app.app_context():
        row = Availability(
            user_id=student_user.user_id,
            term_id=term.term_id,
            day_of_week="Mon",
            start_time=time(9, 0),
            end_time=time(11, 0),
        )
        db.session.add(row)
        db.session.commit()

    resp = client.get(f"/availability/api/v1/availability/export?term_id={term.term_id}")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    cd = resp.headers.get("Content-Disposition", "")
    assert "attachment" in cd
    assert f"availability_term_{term.term_id}.csv" in cd

    body = resp.get_data(as_text=True)
    assert "name,day_of_week,start_time,end_time" in body
    assert student_user.name in body
    assert "Monday" in body
    assert "09:00" in body


def test_export_availability_student_sees_self_only(
    app, client, student_user, supervisor_user, term
):
    """
    GIVEN availability rows for both a supervisor and a student
    WHEN GET /availability/api/v1/availability/export?term_id=<id> is called by the student
    THEN the CSV only contains that student's rows (non-supervisor branch)
    """
    login(client, student_user)

    with app.app_context():
        row1 = Availability(
            user_id=student_user.user_id,
            term_id=term.term_id,
            day_of_week="Mon",
            start_time=time(9, 0),
            end_time=time(11, 0),
        )
        row2 = Availability(
            user_id=supervisor_user.user_id,
            term_id=term.term_id,
            day_of_week="Tue",
            start_time=time(10, 0),
            end_time=time(12, 0),
        )
        db.session.add_all([row1, row2])
        db.session.commit()

    resp = client.get(f"/availability/api/v1/availability/export?term_id={term.term_id}")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)

    # Only the student should appear in the CSV
    assert student_user.name in body
    assert supervisor_user.name not in body


# -------------------------------------------------------------------
# clear_row
# -------------------------------------------------------------------

def test_clear_row_missing_fields(client, supervisor_user):
    """
    GIVEN a logged-in supervisor
    WHEN POST /availability/api/v1/availability/clear-row with missing data
    THEN 400 'term_id and student_name are required' is returned
    """
    login(client, supervisor_user)
    resp = client.post(
        "/availability/api/v1/availability/clear-row",
        json={},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "term_id and student_name are required"


def test_clear_row_user_not_found(client, supervisor_user, term):
    """
    GIVEN an existing term
    WHEN POST /availability/api/v1/availability/clear-row with a non-existent user
    THEN 404 'User ... not found' is returned
    """
    login(client, supervisor_user)
    resp = client.post(
        "/availability/api/v1/availability/clear-row",
        json={"term_id": term.term_id, "student_name": "No One"},
    )
    assert resp.status_code == 404
    assert "User 'No One' not found" in resp.get_json()["error"]


def test_clear_row_success(app, client, supervisor_user, term, student_user):
    """
    GIVEN availability entries for a user in a term
    WHEN POST /availability/api/v1/availability/clear-row is called
    THEN all that user's entries for the term are deleted
    """
    login(client, supervisor_user)
    with app.app_context():
        row = Availability(
            user_id=student_user.user_id,
            term_id=term.term_id,
            day_of_week="Mon",
            start_time=time(9, 0),
            end_time=time(11, 0),
        )
        db.session.add(row)
        db.session.commit()

    resp = client.post(
        "/availability/api/v1/availability/clear-row",
        json={"term_id": term.term_id, "student_name": student_user.name},
    )
    assert resp.status_code == 200
    assert "Cleared availability for" in resp.get_json()["message"]

    with app.app_context():
        assert Availability.query.filter_by(
            user_id=student_user.user_id,
            term_id=term.term_id,
        ).count() == 0


# -------------------------------------------------------------------
# clear_all_availability
# -------------------------------------------------------------------

def test_clear_all_missing_term_id(client, supervisor_user):
    """
    GIVEN a logged-in supervisor
    WHEN POST /availability/api/v1/availability/clear-all without term_id
    THEN 400 'term_id is required' is returned
    """
    login(client, supervisor_user)
    resp = client.post("/availability/api/v1/availability/clear-all", json={})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "term_id is required"


def test_clear_all_term_not_found(client, supervisor_user):
    """
    GIVEN a logged-in supervisor
    WHEN POST /availability/api/v1/availability/clear-all with unknown term_id
    THEN 404 'Term not found' is returned
    """
    login(client, supervisor_user)
    resp = client.post(
        "/availability/api/v1/availability/clear-all",
        json={"term_id": 999},
    )
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "Term not found"


def test_clear_all_success(app, client, supervisor_user, term, student_user):
    """
    GIVEN multiple availability rows for a term
    WHEN POST /availability/api/v1/availability/clear-all is called
    THEN all rows for that term are deleted and the response reports the deleted count
    """
    login(client, supervisor_user)
    with app.app_context():
        # 2 rows for same term/user
        row1 = Availability(
            user_id=student_user.user_id,
            term_id=term.term_id,
            day_of_week="Mon",
            start_time=time(9, 0),
            end_time=time(11, 0),
        )
        row2 = Availability(
            user_id=student_user.user_id,
            term_id=term.term_id,
            day_of_week="Tue",
            start_time=time(10, 0),
            end_time=time(12, 0),
        )
        db.session.add_all([row1, row2])
        db.session.commit()

    resp = client.post(
        "/availability/api/v1/availability/clear-all",
        json={"term_id": term.term_id},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["deleted"] == 2
    assert f"{body['deleted']} availability entries" in body["message"]

    with app.app_context():
        assert Availability.query.filter_by(term_id=term.term_id).count() == 0
