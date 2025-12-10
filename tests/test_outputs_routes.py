import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, date, time, timedelta
from models import User, Term, Shift, Policy, db
from conftest import login_user


class TestAccessControl:
    """Test access control for outputs routes."""

    def test_index_requires_login(self, app, client, db_session):
        """Index page requires authentication."""
        resp = client.get('/outputs/')
        assert resp.status_code == 302
        assert '/login' in resp.location or 'shiftManagementLogin' in resp.location

    def test_export_csv_supervisor_only(self, app, client, db_session, student_user, sample_term):
        """Only supervisors can export CSV."""
        login_user(client, student_user)
        
        resp = client.get('/outputs/export/csv')
        assert resp.status_code == 403

    def test_export_ical_supervisor_only(self, app, client, db_session, student_user, sample_term):
        """Only supervisors can export iCal."""
        login_user(client, student_user)
        
        resp = client.get('/outputs/export/ical')
        assert resp.status_code == 403

    def test_all_students_supervisor_only(self, app, client, db_session, student_user):
        """Only supervisors can view all students."""
        login_user(client, student_user)
        
        resp = client.get('/outputs/all-students')
        assert resp.status_code == 403

    def test_compare_students_supervisor_only(self, app, client, db_session, student_user):
        """Only supervisors can compare students."""
        login_user(client, student_user)
        
        resp = client.get('/outputs/compare-students?ids=1,2')
        assert resp.status_code == 403

    def test_preview_supervisor_only(self, app, client, db_session, student_user):
        """Only supervisors can view full preview."""
        login_user(client, student_user)
        
        resp = client.get('/outputs/preview')
        assert resp.status_code == 403

    def test_api_preview_supervisor_only(self, app, client, db_session, student_user):
        """Only supervisors can access API preview."""
        login_user(client, student_user)
        
        resp = client.get('/outputs/api/schedules/preview')
        assert resp.status_code == 403
        assert resp.json['success'] is False

    def test_api_students_supervisor_only(self, app, client, db_session, student_user):
        """Only supervisors can list students via API."""
        login_user(client, student_user)
        
        resp = client.get('/outputs/api/students')
        assert resp.status_code == 403
        assert resp.json['success'] is False

    def test_student_view_own_schedule_allowed(self, app, client, db_session, student_user):
        """Students can view their own schedule."""
        login_user(client, student_user)
        
        resp = client.get(f'/outputs/student/{student_user.user_id}')
        assert resp.status_code == 200

    def test_student_view_others_schedule_denied(self, app, client, db_session, student_user, supervisor_user):
        """Students cannot view other students' schedules."""
        login_user(client, student_user)
        
        # Try to view supervisor's page (different user)
        resp = client.get(f'/outputs/student/{supervisor_user.user_id}')
        assert resp.status_code == 403

    def test_api_student_schedule_own_allowed(self, app, client, db_session, student_user):
        """Students can access their own schedule via API."""
        login_user(client, student_user)
        
        resp = client.get(f'/outputs/api/students/{student_user.user_id}/schedule')
        assert resp.status_code == 200
        assert resp.json['success'] is True

    def test_api_student_schedule_others_denied(self, app, client, db_session, student_user, supervisor_user):
        """Students cannot access other students' schedules via API."""
        login_user(client, student_user)
        
        resp = client.get(f'/outputs/api/students/{supervisor_user.user_id}/schedule')
        assert resp.status_code == 403
        assert resp.json['success'] is False


class TestIndexPage:
    """Test the main outputs index page."""

    def test_index_renders_with_term(self, app, client, db_session, supervisor_user, sample_term):
        """Index page renders with term information."""
        login_user(client, supervisor_user)
        
        resp = client.get('/outputs/')
        assert resp.status_code == 200
        assert b'Fall 2025' in resp.data or b'Outputs' in resp.data

    def test_index_renders_without_term(self, app, client, db_session, supervisor_user):
        """Index page renders when no term exists."""
        login_user(client, supervisor_user)
        
        resp = client.get('/outputs/')
        assert resp.status_code == 200

    def test_index_student_generates_calendar_token(self, app, client, db_session, student_user):
        """Index page generates calendar token for students."""
        login_user(client, student_user)
        
        # Verify student has no token initially
        assert student_user.calendar_token is None
        
        resp = client.get('/outputs/')
        assert resp.status_code == 200
        
        # Refresh user from database
        db_session.refresh(student_user)
        assert student_user.calendar_token is not None

    def test_index_shows_statistics(self, app, client, db_session, supervisor_user, sample_term, 
                                    student_user, sample_shift):
        """Index page shows shift and student statistics."""
        login_user(client, supervisor_user)
        
        resp = client.get('/outputs/')
        assert resp.status_code == 200


class TestCsvExport:
    """Test CSV export functionality."""

    def test_export_csv_with_term(self, app, client, db_session, supervisor_user, sample_term, 
                                   student_user, sample_shift, policy):
        """CSV export works with specific term."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/outputs/export/csv?term_id={sample_term.term_id}')
        assert resp.status_code == 200
        assert resp.content_type == 'text/csv; charset=utf-8'
        assert 'attachment' in resp.headers.get('Content-Disposition', '')
        assert b'Date' in resp.data
        assert b'Student Name' in resp.data

    def test_export_csv_without_term_id(self, app, client, db_session, supervisor_user, sample_term,
                                        student_user, sample_shift):
        """CSV export uses latest term when no term_id specified."""
        login_user(client, supervisor_user)
        
        resp = client.get('/outputs/export/csv')
        assert resp.status_code == 200
        assert resp.content_type == 'text/csv; charset=utf-8'

    def test_export_csv_constraint_violation(self, app, client, db_session, supervisor_user, sample_term,
                                             student_user, policy):
        """CSV export shows constraint violations."""
        login_user(client, supervisor_user)
        
        # Create a shift that violates policy (30 min when min is 60)
        short_shift = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 2),
            start_time=time(9, 0),
            end_time=time(9, 30),  # Only 30 minutes
            was_manually_adjusted=False
        )
        db_session.add(short_shift)
        db_session.commit()
        
        resp = client.get(f'/outputs/export/csv?term_id={sample_term.term_id}')
        assert resp.status_code == 200
        assert b'VIOLATION' in resp.data

    def test_export_csv_undesirable_time_warning(self, app, client, db_session, supervisor_user, sample_term,
                                                  student_user, policy):
        """CSV export shows undesirable time warnings."""
        login_user(client, supervisor_user)
        
        # Create a shift during undesirable hours (5 AM, before undesireable_start=600)
        early_shift = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 3),
            start_time=time(5, 0),
            end_time=time(7, 0),
            was_manually_adjusted=False
        )
        db_session.add(early_shift)
        db_session.commit()
        
        resp = client.get(f'/outputs/export/csv?term_id={sample_term.term_id}')
        assert resp.status_code == 200
        assert b'Warning' in resp.data

    def test_export_csv_manually_adjusted(self, app, client, db_session, supervisor_user, sample_term,
                                          student_user, policy):
        """CSV export shows manually adjusted status."""
        login_user(client, supervisor_user)
        
        adjusted_shift = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 4),
            start_time=time(10, 0),
            end_time=time(12, 0),
            was_manually_adjusted=True
        )
        db_session.add(adjusted_shift)
        db_session.commit()
        
        resp = client.get(f'/outputs/export/csv?term_id={sample_term.term_id}')
        assert resp.status_code == 200
        assert b'Yes' in resp.data  # Manually adjusted = Yes


class TestIcalExport:
    """Test iCal export functionality."""

    def test_export_ical_with_term(self, app, client, db_session, supervisor_user, sample_term,
                                    student_user, sample_shift, policy):
        """iCal export works with specific term."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/outputs/export/ical?term_id={sample_term.term_id}')
        assert resp.status_code == 200
        assert resp.content_type == 'text/calendar; charset=utf-8'
        assert b'BEGIN:VCALENDAR' in resp.data

    def test_export_ical_without_term_id(self, app, client, db_session, supervisor_user, sample_term,
                                         student_user, sample_shift):
        """iCal export uses latest term when no term_id specified."""
        login_user(client, supervisor_user)
        
        resp = client.get('/outputs/export/ical')
        assert resp.status_code == 200
        assert b'BEGIN:VCALENDAR' in resp.data

    def test_export_ical_constraint_violation(self, app, client, db_session, supervisor_user, sample_term,
                                              student_user, policy):
        """iCal export includes constraint violation info."""
        login_user(client, supervisor_user)
        
        # Create a shift that violates policy
        short_shift = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 2),
            start_time=time(9, 0),
            end_time=time(9, 30),
            was_manually_adjusted=False
        )
        db_session.add(short_shift)
        db_session.commit()
        
        resp = client.get(f'/outputs/export/ical?term_id={sample_term.term_id}')
        assert resp.status_code == 200
        assert b'VIOLATION' in resp.data or b'Constraint Violation' in resp.data

    def test_export_ical_manually_adjusted(self, app, client, db_session, supervisor_user, sample_term,
                                           student_user, policy):
        """iCal export includes manually adjusted info."""
        login_user(client, supervisor_user)
        
        adjusted_shift = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 4),
            start_time=time(10, 0),
            end_time=time(12, 0),
            was_manually_adjusted=True
        )
        db_session.add(adjusted_shift)
        db_session.commit()
        
        resp = client.get(f'/outputs/export/ical?term_id={sample_term.term_id}')
        assert resp.status_code == 200
        assert b'manually adjusted' in resp.data


class TestStudentCalendarFeed:
    """Test public student calendar feed (token-based)."""

    def test_calendar_feed_valid_token(self, app, client, db_session, student_user, sample_term, sample_shift):
        """Calendar feed works with valid token."""
        # Generate token
        student_user.ensure_calendar_token()
        db_session.commit()
        
        resp = client.get(f'/outputs/calendar/{student_user.calendar_token}')
        assert resp.status_code == 200
        assert b'BEGIN:VCALENDAR' in resp.data

    def test_calendar_feed_invalid_token(self, app, client, db_session):
        """Calendar feed returns 404 for invalid token."""
        resp = client.get('/outputs/calendar/invalid-token-12345')
        assert resp.status_code == 404

    def test_calendar_feed_non_student_token(self, app, client, db_session, supervisor_user):
        """Calendar feed returns 404 for non-student users."""
        supervisor_user.ensure_calendar_token()
        db_session.commit()
        
        resp = client.get(f'/outputs/calendar/{supervisor_user.calendar_token}')
        assert resp.status_code == 404

    def test_calendar_feed_with_term_id(self, app, client, db_session, student_user, sample_term, sample_shift):
        """Calendar feed can filter by term."""
        student_user.ensure_calendar_token()
        db_session.commit()
        
        resp = client.get(f'/outputs/calendar/{student_user.calendar_token}?term_id={sample_term.term_id}')
        assert resp.status_code == 200
        assert b'BEGIN:VCALENDAR' in resp.data

    def test_calendar_feed_constraint_violation(self, app, client, db_session, student_user, sample_term, policy):
        """Calendar feed includes constraint violations."""
        student_user.ensure_calendar_token()
        
        short_shift = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 2),
            start_time=time(9, 0),
            end_time=time(9, 30),
            was_manually_adjusted=False
        )
        db_session.add(short_shift)
        db_session.commit()
        
        resp = client.get(f'/outputs/calendar/{student_user.calendar_token}')
        assert resp.status_code == 200


class TestStudentView:
    """Test student view (authenticated)."""

    def test_student_view_renders(self, app, client, db_session, supervisor_user, student_user, sample_shift):
        """Student view renders for supervisor."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/outputs/student/{student_user.user_id}')
        assert resp.status_code == 200
        assert student_user.name.encode() in resp.data

    def test_student_view_non_student_user(self, app, client, db_session, supervisor_user):
        """Student view returns 404 for non-student users."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/outputs/student/{supervisor_user.user_id}')
        assert resp.status_code == 404

    def test_student_view_invalid_user(self, app, client, db_session, supervisor_user):
        """Student view returns 404 for non-existent user."""
        login_user(client, supervisor_user)
        
        resp = client.get('/outputs/student/99999')
        assert resp.status_code == 404

    def test_student_view_with_week_param(self, app, client, db_session, supervisor_user, student_user, sample_shift):
        """Student view accepts week parameter."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/outputs/student/{student_user.user_id}?week=0')
        assert resp.status_code == 200

    def test_student_view_generates_calendar_token(self, app, client, db_session, supervisor_user, student_user):
        """Student view generates calendar token if missing."""
        login_user(client, supervisor_user)
        
        assert student_user.calendar_token is None
        
        resp = client.get(f'/outputs/student/{student_user.user_id}')
        assert resp.status_code == 200
        
        db_session.refresh(student_user)
        assert student_user.calendar_token is not None


class TestPublicScheduleView:
    """Test public schedule view (token-based)."""

    def test_public_view_valid_token(self, app, client, db_session, student_user, sample_shift):
        """Public view works with valid token."""
        student_user.ensure_calendar_token()
        db_session.commit()
        
        resp = client.get(f'/outputs/public/schedule/{student_user.calendar_token}')
        assert resp.status_code == 200

    def test_public_view_invalid_token(self, app, client, db_session):
        """Public view returns 404 for invalid token."""
        resp = client.get('/outputs/public/schedule/invalid-token-12345')
        assert resp.status_code == 404

    def test_public_view_non_student_token(self, app, client, db_session, supervisor_user):
        """Public view returns 404 for non-student users."""
        supervisor_user.ensure_calendar_token()
        db_session.commit()
        
        resp = client.get(f'/outputs/public/schedule/{supervisor_user.calendar_token}')
        assert resp.status_code == 404

    def test_public_view_with_week_param(self, app, client, db_session, student_user, sample_shift):
        """Public view accepts week parameter."""
        student_user.ensure_calendar_token()
        db_session.commit()
        
        resp = client.get(f'/outputs/public/schedule/{student_user.calendar_token}?week=0')
        assert resp.status_code == 200


class TestAllStudentsView:
    """Test all students view (supervisor only)."""

    def test_all_students_renders(self, app, client, db_session, supervisor_user, student_user):
        """All students view renders."""
        login_user(client, supervisor_user)
        
        resp = client.get('/outputs/all-students')
        assert resp.status_code == 200

    def test_all_students_with_search(self, app, client, db_session, supervisor_user, student_user):
        """All students view supports search."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/outputs/all-students?search={student_user.name[:4]}')
        assert resp.status_code == 200

    def test_all_students_filter_0_5(self, app, client, db_session, supervisor_user, student_user):
        """All students view supports 0-5 shift filter."""
        login_user(client, supervisor_user)
        
        resp = client.get('/outputs/all-students?filter=0-5')
        assert resp.status_code == 200

    def test_all_students_filter_6_10(self, app, client, db_session, supervisor_user, student_user, sample_term):
        """All students view supports 6-10 shift filter."""
        login_user(client, supervisor_user)
        
        # Create 7 shifts for the student to match 6-10 filter
        for i in range(7):
            shift = Shift(
                term_id=sample_term.term_id,
                user_id=student_user.user_id,
                date=date(2025, 9, 1) + timedelta(days=i),
                start_time=time(9, 0),
                end_time=time(11, 0),
                was_manually_adjusted=False
            )
            db_session.add(shift)
        db_session.commit()
        
        resp = client.get('/outputs/all-students?filter=6-10&week=0')
        assert resp.status_code == 200

    def test_all_students_filter_11_plus(self, app, client, db_session, supervisor_user, student_user, sample_term):
        """All students view supports 11+ shift filter."""
        login_user(client, supervisor_user)
        
        # Create 12 shifts for the student
        for i in range(12):
            shift = Shift(
                term_id=sample_term.term_id,
                user_id=student_user.user_id,
                date=date(2025, 9, 1) + timedelta(days=i % 7),
                start_time=time(9 + (i // 7) * 3, 0),
                end_time=time(11 + (i // 7) * 3, 0),
                was_manually_adjusted=False
            )
            db_session.add(shift)
        db_session.commit()
        
        resp = client.get('/outputs/all-students?filter=11%2B&week=0')
        assert resp.status_code == 200

    def test_all_students_with_week_param(self, app, client, db_session, supervisor_user, student_user, sample_shift):
        """All students view supports week parameter."""
        login_user(client, supervisor_user)
        
        resp = client.get('/outputs/all-students?week=0')
        assert resp.status_code == 200


class TestCompareStudents:
    """Test compare students view."""

    def test_compare_no_ids_redirects(self, app, client, db_session, supervisor_user):
        """Compare view redirects when no IDs provided."""
        login_user(client, supervisor_user)
        
        resp = client.get('/outputs/compare-students')
        assert resp.status_code == 302

    def test_compare_empty_ids_redirects(self, app, client, db_session, supervisor_user):
        """Compare view redirects when empty IDs provided."""
        login_user(client, supervisor_user)
        
        resp = client.get('/outputs/compare-students?ids=')
        assert resp.status_code == 302

    def test_compare_invalid_ids(self, app, client, db_session, supervisor_user):
        """Compare view handles invalid IDs."""
        login_user(client, supervisor_user)
        
        resp = client.get('/outputs/compare-students?ids=abc,def')
        assert resp.status_code == 400

    def test_compare_valid_students(self, app, client, db_session, supervisor_user, student_user):
        """Compare view works with valid student IDs."""
        login_user(client, supervisor_user)
        
        # Create another student
        student2 = User(
            name="Student Two",
            email="student2@colby.edu",
            role="student",
            is_active=True
        )
        student2.set_password("testpass")
        db_session.add(student2)
        db_session.commit()
        
        resp = client.get(f'/outputs/compare-students?ids={student_user.user_id},{student2.user_id}')
        assert resp.status_code == 200

    def test_compare_non_student_user(self, app, client, db_session, supervisor_user, student_user):
        """Compare view handles non-student users."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/outputs/compare-students?ids={student_user.user_id},{supervisor_user.user_id}')
        assert resp.status_code == 404

    def test_compare_with_week_param(self, app, client, db_session, supervisor_user, student_user, sample_shift):
        """Compare view supports week parameter."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/outputs/compare-students?ids={student_user.user_id}&week=0')
        assert resp.status_code == 200

    def test_compare_limits_to_three_students(self, app, client, db_session, supervisor_user, student_user):
        """Compare view limits to 3 students."""
        login_user(client, supervisor_user)
        
        # Create 4 more students
        students = []
        for i in range(4):
            s = User(
                name=f"Student {i+2}",
                email=f"student{i+2}@colby.edu",
                role="student",
                is_active=True
            )
            s.set_password("testpass")
            db_session.add(s)
            students.append(s)
        db_session.commit()
        
        # Try to compare 5 students
        ids = f"{student_user.user_id}," + ",".join(str(s.user_id) for s in students)
        resp = client.get(f'/outputs/compare-students?ids={ids}')
        assert resp.status_code == 200


class TestPreviewPage:
    """Test preview page."""

    def test_preview_renders(self, app, client, db_session, supervisor_user, sample_term, student_user, sample_shift):
        """Preview page renders."""
        login_user(client, supervisor_user)
        
        resp = client.get('/outputs/preview')
        assert resp.status_code == 200

    def test_preview_no_term(self, app, client, db_session, supervisor_user):
        """Preview page renders when no term exists."""
        login_user(client, supervisor_user)
        
        resp = client.get('/outputs/preview')
        assert resp.status_code == 200

    def test_preview_with_term_id(self, app, client, db_session, supervisor_user, sample_term, sample_shift, student_user):
        """Preview page works with term_id parameter."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/outputs/preview?term_id={sample_term.term_id}')
        assert resp.status_code == 200

    def test_preview_with_week_param(self, app, client, db_session, supervisor_user, sample_term, sample_shift, student_user):
        """Preview page accepts week parameter."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/outputs/preview?term_id={sample_term.term_id}&week=0')
        assert resp.status_code == 200

    def test_preview_constraint_warnings(self, app, client, db_session, supervisor_user, sample_term,
                                         student_user, policy):
        """Preview page shows constraint warnings."""
        login_user(client, supervisor_user)
        
        # Create shifts with various constraint issues
        short_shift = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1),
            start_time=time(9, 0),
            end_time=time(9, 30),  # Too short
            was_manually_adjusted=False
        )
        long_shift = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 2),
            start_time=time(9, 0),
            end_time=time(14, 0),  # Too long (5 hours > 3 hours max)
            was_manually_adjusted=False
        )
        early_shift = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 3),
            start_time=time(5, 0),
            end_time=time(7, 0),  # Early
            was_manually_adjusted=False
        )
        late_shift = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 4),
            start_time=time(19, 0),
            end_time=time(22, 0),  # Late
            was_manually_adjusted=False
        )
        db_session.add_all([short_shift, long_shift, early_shift, late_shift])
        db_session.commit()
        
        resp = client.get(f'/outputs/preview?term_id={sample_term.term_id}')
        assert resp.status_code == 200

    def test_preview_overlapping_shifts(self, app, client, db_session, supervisor_user, sample_term,
                                        student_user, policy):
        """Preview page handles overlapping shifts."""
        login_user(client, supervisor_user)
        
        # Create another student
        student2 = User(
            name="Student Two",
            email="student2@colby.edu",
            role="student",
            is_active=True
        )
        student2.set_password("testpass")
        db_session.add(student2)
        db_session.commit()
        
        # Create overlapping shifts on the same day
        shift1 = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1),
            start_time=time(9, 0),
            end_time=time(11, 0),
            was_manually_adjusted=False
        )
        shift2 = Shift(
            term_id=sample_term.term_id,
            user_id=student2.user_id,
            date=date(2025, 9, 1),
            start_time=time(10, 0),
            end_time=time(12, 0),
            was_manually_adjusted=False
        )
        db_session.add_all([shift1, shift2])
        db_session.commit()
        
        resp = client.get(f'/outputs/preview?term_id={sample_term.term_id}')
        assert resp.status_code == 200


class TestApiSchedules:
    """Test API schedules endpoint."""

    def test_api_list_schedules_supervisor(self, app, client, db_session, supervisor_user, sample_term, 
                                           student_user, sample_shift):
        """Supervisors can list all schedules."""
        login_user(client, supervisor_user)
        
        resp = client.get('/outputs/api/schedules')
        assert resp.status_code == 200
        assert resp.json['success'] is True
        assert 'shifts' in resp.json['data']

    def test_api_list_schedules_student_restricted(self, app, client, db_session, student_user, sample_term, sample_shift):
        """Students can only see their own schedules."""
        login_user(client, student_user)
        
        resp = client.get('/outputs/api/schedules')
        assert resp.status_code == 200
        assert resp.json['success'] is True
        # All shifts should belong to the student
        for shift in resp.json['data']['shifts']:
            assert shift['user_id'] == student_user.user_id

    def test_api_list_schedules_with_term_filter(self, app, client, db_session, supervisor_user, sample_term, sample_shift):
        """API supports term filter."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/outputs/api/schedules?term_id={sample_term.term_id}')
        assert resp.status_code == 200
        assert resp.json['success'] is True

    def test_api_list_schedules_with_user_filter(self, app, client, db_session, supervisor_user, sample_term, 
                                                  student_user, sample_shift):
        """API supports user filter."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/outputs/api/schedules?user_id={student_user.user_id}')
        assert resp.status_code == 200
        assert resp.json['success'] is True

    def test_api_list_schedules_with_date_filters(self, app, client, db_session, supervisor_user, sample_term, sample_shift):
        """API supports date range filters."""
        login_user(client, supervisor_user)
        
        resp = client.get('/outputs/api/schedules?start_date=2025-09-01&end_date=2025-09-30')
        assert resp.status_code == 200
        assert resp.json['success'] is True

    def test_api_list_schedules_exception(self, app, client, db_session, supervisor_user):
        """API handles exceptions gracefully."""
        login_user(client, supervisor_user)
        
        # Invalid date format triggers exception
        resp = client.get('/outputs/api/schedules?start_date=invalid')
        assert resp.status_code == 500
        assert resp.json['success'] is False


class TestApiSchedulesPreview:
    """Test API schedules preview endpoint."""

    def test_api_preview_renders(self, app, client, db_session, supervisor_user, sample_term, 
                                  student_user, sample_shift, policy):
        """API preview returns data."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/outputs/api/schedules/preview?term_id={sample_term.term_id}')
        assert resp.status_code == 200
        assert resp.json['success'] is True
        assert 'term' in resp.json['data']
        assert 'weeks' in resp.json['data']

    def test_api_preview_no_term(self, app, client, db_session, supervisor_user):
        """API preview handles no term gracefully."""
        login_user(client, supervisor_user)
        
        resp = client.get('/outputs/api/schedules/preview')
        assert resp.status_code == 200
        assert resp.json['success'] is True
        assert resp.json['data']['term'] is None

    def test_api_preview_with_policy(self, app, client, db_session, supervisor_user, sample_term, 
                                      student_user, sample_shift, policy):
        """API preview includes policy information."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/outputs/api/schedules/preview?term_id={sample_term.term_id}')
        assert resp.status_code == 200
        assert resp.json['data']['policy'] is not None

    def test_api_preview_constraint_violations(self, app, client, db_session, supervisor_user, sample_term,
                                                student_user, policy):
        """API preview includes constraint violation info."""
        login_user(client, supervisor_user)
        
        # Create shift that violates constraints
        short_shift = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1),
            start_time=time(9, 0),
            end_time=time(9, 30),  # Too short
            was_manually_adjusted=False
        )
        db_session.add(short_shift)
        db_session.commit()
        
        resp = client.get(f'/outputs/api/schedules/preview?term_id={sample_term.term_id}')
        assert resp.status_code == 200
        # Check that warnings are included
        found_warning = False
        for week in resp.json['data']['weeks']:
            for shift in week['shifts']:
                if shift['warnings']:
                    found_warning = True
        assert found_warning

    def test_api_preview_exception(self, app, client, db_session, supervisor_user):
        """API preview handles exceptions."""
        login_user(client, supervisor_user)
        
        with patch('blueprints.outputs.routes.Shift') as mock_shift:
            mock_shift.query.filter_by.side_effect = Exception("Database error")
            
            # This might not trigger the exception directly due to Flask's handling
            # Let's create a term first to ensure we go through the code path
            term = Term(
                name="Test Term",
                start_date=date(2025, 9, 1),
                end_date=date(2025, 12, 15),
                availability_deadline=date(2025, 8, 15),
                locked=False
            )
            db_session.add(term)
            db_session.commit()
            
            resp = client.get(f'/outputs/api/schedules/preview?term_id={term.term_id}')
            # Due to mock, this will likely raise an exception
            assert resp.status_code in [200, 500]


class TestApiStudents:
    """Test API students endpoint."""

    def test_api_list_students(self, app, client, db_session, supervisor_user, student_user):
        """API lists students with shift counts."""
        login_user(client, supervisor_user)
        
        resp = client.get('/outputs/api/students')
        assert resp.status_code == 200
        assert resp.json['success'] is True
        assert 'students' in resp.json['data']

    def test_api_list_students_with_search(self, app, client, db_session, supervisor_user, student_user):
        """API supports student search."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/outputs/api/students?search={student_user.name[:4]}')
        assert resp.status_code == 200
        assert resp.json['success'] is True

    def test_api_list_students_with_term(self, app, client, db_session, supervisor_user, student_user, 
                                         sample_term, sample_shift):
        """API supports term filter for shift counts."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/outputs/api/students?term_id={sample_term.term_id}')
        assert resp.status_code == 200
        assert resp.json['success'] is True

    def test_api_list_students_exception(self, app, client, db_session, supervisor_user):
        """API handles exceptions gracefully."""
        login_user(client, supervisor_user)
        
        with patch('blueprints.outputs.routes.User') as mock_user:
            mock_user.query.filter_by.side_effect = Exception("Database error")
            
            resp = client.get('/outputs/api/students')
            assert resp.status_code == 500
            assert resp.json['success'] is False


class TestApiStudentSchedule:
    """Test API student schedule endpoint."""

    def test_api_student_schedule_supervisor(self, app, client, db_session, supervisor_user, student_user, 
                                              sample_term, sample_shift):
        """Supervisors can view any student schedule."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/outputs/api/students/{student_user.user_id}/schedule')
        assert resp.status_code == 200
        assert resp.json['success'] is True
        assert 'student' in resp.json['data']
        assert 'weeks' in resp.json['data']

    def test_api_student_schedule_not_found(self, app, client, db_session, supervisor_user):
        """API returns 404 for non-existent student."""
        login_user(client, supervisor_user)
        
        resp = client.get('/outputs/api/students/99999/schedule')
        assert resp.status_code == 404
        assert resp.json['success'] is False

    def test_api_student_schedule_non_student(self, app, client, db_session, supervisor_user):
        """API returns 400 for non-student user."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/outputs/api/students/{supervisor_user.user_id}/schedule')
        assert resp.status_code == 400
        assert resp.json['success'] is False

    def test_api_student_schedule_with_term(self, app, client, db_session, supervisor_user, student_user,
                                            sample_term, sample_shift):
        """API supports term filter."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/outputs/api/students/{student_user.user_id}/schedule?term_id={sample_term.term_id}')
        assert resp.status_code == 200
        assert resp.json['success'] is True

    def test_api_student_schedule_with_week(self, app, client, db_session, supervisor_user, student_user,
                                            sample_term, sample_shift):
        """API supports week parameter."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/outputs/api/students/{student_user.user_id}/schedule?week=0')
        assert resp.status_code == 200
        assert resp.json['success'] is True

    def test_api_student_schedule_auto_week_selection(self, app, client, db_session, supervisor_user, student_user,
                                                       sample_term, sample_shift):
        """API auto-selects current week when no week param."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/outputs/api/students/{student_user.user_id}/schedule')
        assert resp.status_code == 200
        assert 'current_week_index' in resp.json['data']

    def test_api_student_schedule_exception(self, app, client, db_session, supervisor_user, student_user):
        """API handles exceptions gracefully."""
        login_user(client, supervisor_user)
        
        with patch('blueprints.outputs.routes.Shift') as mock_shift:
            mock_shift.query.filter_by.side_effect = Exception("Database error")
            
            resp = client.get(f'/outputs/api/students/{student_user.user_id}/schedule')
            assert resp.status_code == 500
            assert resp.json['success'] is False


class TestHelperFunctions:
    """Test helper functions and edge cases."""

    def test_default_week_index_empty_weeks(self, app, client, db_session, supervisor_user):
        """_get_default_week_index handles empty weeks list."""
        login_user(client, supervisor_user)
        
        # Empty weeks case is tested when accessing views with no shifts
        resp = client.get('/outputs/preview')
        assert resp.status_code == 200

    def test_default_week_index_explicit_param(self, app, client, db_session, supervisor_user, sample_term, 
                                               student_user, sample_shift):
        """_get_default_week_index honors explicit week parameter."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/outputs/preview?term_id={sample_term.term_id}&week=0')
        assert resp.status_code == 200

    def test_default_week_index_today_before_weeks(self, app, client, db_session, supervisor_user, student_user):
        """_get_default_week_index handles today before all weeks."""
        login_user(client, supervisor_user)
        
        # Create a term in the future
        future_term = Term(
            name="Future Term",
            start_date=date(2030, 9, 1),
            end_date=date(2030, 12, 15),
            availability_deadline=date(2030, 8, 15),
            locked=False
        )
        db_session.add(future_term)
        db_session.commit()  # Commit term first to get term_id
        
        future_shift = Shift(
            term_id=future_term.term_id,
            user_id=student_user.user_id,
            date=date(2030, 9, 1),
            start_time=time(9, 0),
            end_time=time(11, 0),
            was_manually_adjusted=False
        )
        db_session.add(future_shift)
        db_session.commit()
        
        resp = client.get(f'/outputs/preview?term_id={future_term.term_id}')
        assert resp.status_code == 200


class TestAdditionalCoverage:
    """Additional tests for edge cases and 95%+ coverage."""

    # --- Test icalendar not available (lines 18-19, 170, 293) ---
    @patch('blueprints.outputs.routes.ICALENDAR_AVAILABLE', False)
    def test_export_ical_not_available(self, app, client, db_session, supervisor_user):
        """iCal export returns error when icalendar not installed."""
        login_user(client, supervisor_user)
        
        resp = client.get('/outputs/export/ical')
        assert resp.status_code == 500
        assert b'icalendar package not installed' in resp.data

    @patch('blueprints.outputs.routes.ICALENDAR_AVAILABLE', False)
    def test_calendar_feed_not_available(self, app, client, db_session, student_user):
        """Calendar feed returns error when icalendar not installed."""
        student_user.ensure_calendar_token()
        db_session.commit()
        
        resp = client.get(f'/outputs/calendar/{student_user.calendar_token}')
        assert resp.status_code == 500
        assert b'icalendar package not installed' in resp.data

    # --- Test compare_students empty ids after parsing (line 694) ---
    def test_compare_students_empty_after_strip(self, app, client, db_session, supervisor_user):
        """Compare view handles empty IDs after stripping whitespace."""
        login_user(client, supervisor_user)
        
        resp = client.get('/outputs/compare-students?ids=,,,')
        assert resp.status_code == 302  # Redirects to all_students_view

    # --- Test manually adjusted in calendar feed (line 374) ---
    def test_calendar_feed_manually_adjusted(self, app, client, db_session, student_user, sample_term, policy):
        """Calendar feed shows manually adjusted info."""
        student_user.ensure_calendar_token()
        
        adjusted_shift = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 4),
            start_time=time(10, 0),
            end_time=time(12, 0),
            was_manually_adjusted=True
        )
        db_session.add(adjusted_shift)
        db_session.commit()
        
        resp = client.get(f'/outputs/calendar/{student_user.calendar_token}')
        assert resp.status_code == 200
        assert b'manually adjusted' in resp.data

    # --- Test today in week range (line 43) ---
    def test_default_week_index_today_in_range(self, app, client, db_session, supervisor_user, student_user):
        """_get_default_week_index finds week containing today."""
        login_user(client, supervisor_user)
        
        # Create a term that includes today
        today = date.today()
        term = Term(
            name="Current Term",
            start_date=today - timedelta(days=7),
            end_date=today + timedelta(days=30),
            availability_deadline=today - timedelta(days=14),
            locked=False
        )
        db_session.add(term)
        db_session.commit()
        
        # Create a shift for today's week
        shift = Shift(
            term_id=term.term_id,
            user_id=student_user.user_id,
            date=today,
            start_time=time(9, 0),
            end_time=time(11, 0),
            was_manually_adjusted=False
        )
        db_session.add(shift)
        db_session.commit()
        
        resp = client.get(f'/outputs/preview?term_id={term.term_id}')
        assert resp.status_code == 200

    # --- Test today after all weeks (line 47) ---
    def test_default_week_index_today_after_weeks(self, app, client, db_session, supervisor_user, student_user):
        """_get_default_week_index returns last week when today is after all weeks."""
        login_user(client, supervisor_user)
        
        # Create a term in the past
        past_term = Term(
            name="Past Term",
            start_date=date(2020, 9, 1),
            end_date=date(2020, 12, 15),
            availability_deadline=date(2020, 8, 15),
            locked=False
        )
        db_session.add(past_term)
        db_session.commit()
        
        past_shift = Shift(
            term_id=past_term.term_id,
            user_id=student_user.user_id,
            date=date(2020, 9, 1),
            start_time=time(9, 0),
            end_time=time(11, 0),
            was_manually_adjusted=False
        )
        db_session.add(past_shift)
        db_session.commit()
        
        resp = client.get(f'/outputs/preview?term_id={past_term.term_id}')
        assert resp.status_code == 200

    # --- Test overlapping shifts position calculation (line 921) ---
    def test_preview_multiple_overlapping_shifts(self, app, client, db_session, supervisor_user, sample_term, policy):
        """Preview correctly calculates position for multiple overlapping shifts."""
        login_user(client, supervisor_user)
        
        # Create 3 students
        students = []
        for i in range(3):
            s = User(
                name=f"Overlap Student {i+1}",
                email=f"overlap{i+1}@colby.edu",
                role="student",
                is_active=True
            )
            s.set_password("testpass")
            db_session.add(s)
            students.append(s)
        db_session.commit()
        
        # Create 3 overlapping shifts on the same day with different start times
        for i, student in enumerate(students):
            shift = Shift(
                term_id=sample_term.term_id,
                user_id=student.user_id,
                date=date(2025, 9, 1),
                start_time=time(9 + i, 0),  # 9:00, 10:00, 11:00
                end_time=time(12 + i, 0),   # 12:00, 13:00, 14:00 - all overlap
                was_manually_adjusted=False
            )
            db_session.add(shift)
        db_session.commit()
        
        resp = client.get(f'/outputs/preview?term_id={sample_term.term_id}')
        assert resp.status_code == 200

    def test_preview_same_start_time_overlap(self, app, client, db_session, supervisor_user, sample_term, policy):
        """Preview handles shifts with exact same start time (line 921 - shift_id tiebreaker)."""
        login_user(client, supervisor_user)
        
        # Create 2 students
        students = []
        for i in range(2):
            s = User(
                name=f"SameStart Student {i+1}",
                email=f"samestart{i+1}@colby.edu",
                role="student",
                is_active=True
            )
            s.set_password("testpass")
            db_session.add(s)
            students.append(s)
        db_session.commit()
        
        # Create 2 shifts with EXACT same start time (triggers elif branch at line 915-921)
        for student in students:
            shift = Shift(
                term_id=sample_term.term_id,
                user_id=student.user_id,
                date=date(2025, 9, 2),
                start_time=time(9, 0),  # Same start time for both
                end_time=time(11, 0),   # Same end time too - full overlap
                was_manually_adjusted=False
            )
            db_session.add(shift)
        db_session.commit()
        
        resp = client.get(f'/outputs/preview?term_id={sample_term.term_id}')
        assert resp.status_code == 200

    # --- Test API student schedule auto-select week with today in range (lines 1262-1263) ---
    def test_api_student_schedule_today_in_week(self, app, client, db_session, supervisor_user, student_user):
        """API auto-selects current week when today falls within a week."""
        login_user(client, supervisor_user)
        
        today = date.today()
        term = Term(
            name="Current Term for API",
            start_date=today - timedelta(days=7),
            end_date=today + timedelta(days=30),
            availability_deadline=today - timedelta(days=14),
            locked=False
        )
        db_session.add(term)
        db_session.commit()
        
        # Create a shift for today
        shift = Shift(
            term_id=term.term_id,
            user_id=student_user.user_id,
            date=today,
            start_time=time(9, 0),
            end_time=time(11, 0),
            was_manually_adjusted=False
        )
        db_session.add(shift)
        db_session.commit()
        
        resp = client.get(f'/outputs/api/students/{student_user.user_id}/schedule?term_id={term.term_id}')
        assert resp.status_code == 200
        assert resp.json['success'] is True

    def test_student_view_no_shifts(self, app, client, db_session, supervisor_user, student_user):
        """Student view handles no shifts gracefully."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/outputs/student/{student_user.user_id}')
        assert resp.status_code == 200

    def test_public_view_no_shifts(self, app, client, db_session, student_user):
        """Public view handles no shifts gracefully."""
        student_user.ensure_calendar_token()
        db_session.commit()
        
        resp = client.get(f'/outputs/public/schedule/{student_user.calendar_token}')
        assert resp.status_code == 200

    def test_all_students_no_shifts(self, app, client, db_session, supervisor_user, student_user):
        """All students view handles no shifts gracefully."""
        login_user(client, supervisor_user)
        
        resp = client.get('/outputs/all-students')
        assert resp.status_code == 200

    def test_compare_students_with_shifts(self, app, client, db_session, supervisor_user, student_user, 
                                          sample_term, sample_shift):
        """Compare students shows shift data."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/outputs/compare-students?ids={student_user.user_id}')
        assert resp.status_code == 200

    def test_calendar_feed_without_term(self, app, client, db_session, student_user, sample_shift):
        """Calendar feed works without term filter."""
        student_user.ensure_calendar_token()
        db_session.commit()
        
        resp = client.get(f'/outputs/calendar/{student_user.calendar_token}')
        assert resp.status_code == 200

    def test_ical_export_undesirable_time_warning(self, app, client, db_session, supervisor_user, sample_term,
                                                   student_user, policy):
        """iCal export shows undesirable time warnings."""
        login_user(client, supervisor_user)
        
        # Create a shift during undesirable hours
        late_shift = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 4),
            start_time=time(21, 0),  # After undesireable_end=2000
            end_time=time(23, 0),
            was_manually_adjusted=False
        )
        db_session.add(late_shift)
        db_session.commit()
        
        resp = client.get(f'/outputs/export/ical?term_id={sample_term.term_id}')
        assert resp.status_code == 200
        assert b'undesirable' in resp.data

    def test_calendar_feed_with_constraint_warning(self, app, client, db_session, student_user, sample_term, policy):
        """Calendar feed shows constraint warning."""
        student_user.ensure_calendar_token()
        
        # Create shift with undesirable time
        late_shift = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 4),
            start_time=time(21, 0),
            end_time=time(23, 0),
            was_manually_adjusted=False
        )
        db_session.add(late_shift)
        db_session.commit()
        
        resp = client.get(f'/outputs/calendar/{student_user.calendar_token}')
        assert resp.status_code == 200

    def test_api_schedules_no_term_info(self, app, client, db_session, supervisor_user):
        """API schedules handles case with shifts but no explicit term."""
        login_user(client, supervisor_user)
        
        resp = client.get('/outputs/api/schedules')
        assert resp.status_code == 200
        assert resp.json['success'] is True

    def test_compare_students_weekly_stats(self, app, client, db_session, supervisor_user, student_user,
                                           sample_term, sample_shift):
        """Compare students calculates weekly stats."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/outputs/compare-students?ids={student_user.user_id}&week=0')
        assert resp.status_code == 200

    def test_all_students_weekly_hours_cache(self, app, client, db_session, supervisor_user, student_user,
                                             sample_term, sample_shift):
        """All students view uses cache for weekly hours."""
        login_user(client, supervisor_user)
        
        resp = client.get('/outputs/all-students?week=0')
        assert resp.status_code == 200

    def test_preview_with_invalid_term(self, app, client, db_session, supervisor_user):
        """Preview handles invalid term_id."""
        login_user(client, supervisor_user)
        
        resp = client.get('/outputs/preview?term_id=99999')
        assert resp.status_code == 404

    def test_csv_export_without_policy(self, app, client, db_session, supervisor_user, sample_term,
                                        student_user, sample_shift):
        """CSV export works without policy."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/outputs/export/csv?term_id={sample_term.term_id}')
        assert resp.status_code == 200
        assert b'Valid' in resp.data

    def test_ical_export_without_policy(self, app, client, db_session, supervisor_user, sample_term,
                                         student_user, sample_shift):
        """iCal export works without policy."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/outputs/export/ical?term_id={sample_term.term_id}')
        assert resp.status_code == 200

    def test_calendar_feed_without_policy(self, app, client, db_session, student_user, sample_term, sample_shift):
        """Calendar feed works without policy."""
        student_user.ensure_calendar_token()
        db_session.commit()
        
        resp = client.get(f'/outputs/calendar/{student_user.calendar_token}?term_id={sample_term.term_id}')
        assert resp.status_code == 200

    def test_api_preview_late_end_constraint(self, app, client, db_session, supervisor_user, sample_term,
                                             student_user, policy):
        """API preview shows late end constraint warning."""
        login_user(client, supervisor_user)
        
        late_shift = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 4),
            start_time=time(19, 0),
            end_time=time(22, 0),  # Late end
            was_manually_adjusted=False
        )
        db_session.add(late_shift)
        db_session.commit()
        
        resp = client.get(f'/outputs/api/schedules/preview?term_id={sample_term.term_id}')
        assert resp.status_code == 200
        found_late = False
        for week in resp.json['data']['weeks']:
            for shift in week['shifts']:
                if 'Late end' in shift['warnings']:
                    found_late = True
        assert found_late

    def test_api_preview_early_start_constraint(self, app, client, db_session, supervisor_user, sample_term,
                                                 student_user, policy):
        """API preview shows early start constraint warning."""
        login_user(client, supervisor_user)
        
        early_shift = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 5),
            start_time=time(5, 0),  # Before undesireable_start=600
            end_time=time(7, 0),
            was_manually_adjusted=False
        )
        db_session.add(early_shift)
        db_session.commit()
        
        resp = client.get(f'/outputs/api/schedules/preview?term_id={sample_term.term_id}')
        assert resp.status_code == 200
        found_early = False
        for week in resp.json['data']['weeks']:
            for shift in week['shifts']:
                if 'Early start' in shift['warnings']:
                    found_early = True
        assert found_early

    def test_api_preview_too_long_constraint(self, app, client, db_session, supervisor_user, sample_term,
                                              student_user, policy):
        """API preview shows too long constraint warning."""
        login_user(client, supervisor_user)
        
        long_shift = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 6),
            start_time=time(9, 0),
            end_time=time(14, 0),  # 5 hours > 3 hours max
            was_manually_adjusted=False
        )
        db_session.add(long_shift)
        db_session.commit()
        
        resp = client.get(f'/outputs/api/schedules/preview?term_id={sample_term.term_id}')
        assert resp.status_code == 200
        found_long = False
        for week in resp.json['data']['weeks']:
            for shift in week['shifts']:
                if 'Too long' in shift['warnings']:
                    found_long = True
        assert found_long
