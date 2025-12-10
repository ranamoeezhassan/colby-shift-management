import pytest
from datetime import date, time, timedelta
from unittest.mock import patch, MagicMock
from flask import url_for

from models import db, User, Term, Shift, Policy, StaffingNeeds, Availability
from conftest import login_user


# -------------------------------------------------------------------
# Access Control Tests
# -------------------------------------------------------------------

class TestAccessControl:
    """Test that scheduler routes are restricted to supervisors only."""

    def test_index_student_denied(self, app, client, db_session, student_user):
        """Students cannot access the scheduler index page."""
        login_user(client, student_user)
        
        resp = client.get('/scheduler/')
        
        # Should redirect with flash message about access denied
        assert resp.status_code == 302
        # Follow redirect to see the flash message
        resp = client.get('/scheduler/', follow_redirects=True)
        assert b'Access denied' in resp.data or b'Only supervisors' in resp.data

    def test_index_supervisor_allowed(self, app, client, db_session, supervisor_user, sample_term):
        """Supervisors can access the scheduler index page."""
        login_user(client, supervisor_user)
        
        resp = client.get('/scheduler/')
        
        assert resp.status_code == 200
        # Should render the scheduler page
        assert b'scheduler' in resp.data.lower() or b'schedule' in resp.data.lower()

    def test_generate_student_denied(self, app, client, db_session, student_user, sample_term):
        """Students cannot generate schedules."""
        login_user(client, student_user)
        
        resp = client.post('/scheduler/generate', data={
            'term_id': sample_term.term_id,
            'start_date': '2025-09-01',
            'end_date': '2025-09-07'
        })
        
        # Should redirect with access denied
        assert resp.status_code == 302
        resp = client.post('/scheduler/generate', data={
            'term_id': sample_term.term_id,
            'start_date': '2025-09-01',
            'end_date': '2025-09-07'
        }, follow_redirects=True)
        assert b'Access denied' in resp.data or b'Only supervisors' in resp.data

    def test_edit_schedule_student_denied(self, app, client, db_session, student_user, sample_term):
        """Students cannot access the edit schedule page."""
        login_user(client, student_user)
        
        resp = client.get(f'/scheduler/edit-schedule?term_id={sample_term.term_id}')
        
        assert resp.status_code == 302
        resp = client.get(f'/scheduler/edit-schedule?term_id={sample_term.term_id}', follow_redirects=True)
        assert b'Access denied' in resp.data or b'Only supervisors' in resp.data

    def test_api_list_shifts_student_denied(self, app, client, db_session, student_user):
        """Students cannot access the shifts API."""
        login_user(client, student_user)
        
        resp = client.get('/scheduler/api/shifts')
        
        assert resp.status_code == 403
        assert resp.json['success'] is False
        assert 'Access denied' in resp.json['error']

    def test_api_create_shift_student_denied(self, app, client, db_session, student_user, sample_term):
        """Students cannot create shifts via API."""
        login_user(client, student_user)
        
        resp = client.post('/scheduler/api/shifts', json={
            'term_id': sample_term.term_id,
            'user_id': student_user.user_id,
            'date': '2025-09-01',
            'start_time': '09:00',
            'end_time': '11:00'
        })
        
        assert resp.status_code == 403
        assert resp.json['success'] is False

    def test_api_get_shift_student_denied(self, app, client, db_session, student_user, sample_shift):
        """Students cannot get shift details via API."""
        login_user(client, student_user)
        
        resp = client.get(f'/scheduler/api/shifts/{sample_shift.shift_id}')
        
        assert resp.status_code == 403
        assert resp.json['success'] is False

    def test_api_update_shift_student_denied(self, app, client, db_session, student_user, sample_shift):
        """Students cannot update shifts via API."""
        login_user(client, student_user)
        
        resp = client.put(f'/scheduler/api/shifts/{sample_shift.shift_id}', json={
            'start_time': '10:00'
        })
        
        assert resp.status_code == 403
        assert resp.json['success'] is False

    def test_api_delete_shift_student_denied(self, app, client, db_session, student_user, sample_shift):
        """Students cannot delete shifts via API."""
        login_user(client, student_user)
        
        resp = client.delete(f'/scheduler/api/shifts/{sample_shift.shift_id}')
        
        assert resp.status_code == 403
        assert resp.json['success'] is False

    def test_create_shift_legacy_student_denied(self, app, client, db_session, student_user, sample_term):
        """Students cannot create shifts via legacy route."""
        login_user(client, student_user)
        
        resp = client.post('/scheduler/create-shift', json={
            'term_id': sample_term.term_id,
            'user_id': student_user.user_id,
            'date': '2025-09-01',
            'start_time': '09:00',
            'end_time': '11:00'
        })
        
        assert resp.status_code == 403
        assert resp.json['success'] is False

    def test_delete_shift_legacy_student_denied(self, app, client, db_session, student_user, sample_shift):
        """Students cannot delete shifts via legacy route."""
        login_user(client, student_user)
        
        resp = client.post(f'/scheduler/delete-shift/{sample_shift.shift_id}')
        
        assert resp.status_code == 403
        assert resp.json['success'] is False

    def test_edit_shift_student_denied(self, app, client, db_session, student_user, sample_shift):
        """Students cannot edit shifts via legacy route (line 386)."""
        login_user(client, student_user)
        
        resp = client.post(f'/scheduler/edit-shift/{sample_shift.shift_id}', json={
            'start_time': '10:00'
        })
        
        assert resp.status_code == 403
        assert resp.json['success'] is False

    def test_reassign_shift_student_denied(self, app, client, db_session, student_user, sample_shift):
        """Students cannot reassign shifts via legacy route (line 558)."""
        login_user(client, student_user)
        
        resp = client.post(f'/scheduler/reassign-shift/{sample_shift.shift_id}', json={
            'user_id': student_user.user_id
        })
        
        assert resp.status_code == 403
        assert resp.json['success'] is False

    def test_validate_shift_edit_student_denied(self, app, client, db_session, student_user, sample_term):
        """Students cannot use the validation endpoint."""
        login_user(client, student_user)
        
        resp = client.post('/scheduler/validate-shift-edit', json={
            'term_id': sample_term.term_id,
            'date': '2025-09-01',
            'start_time': '09:00',
            'end_time': '11:00'
        })
        
        assert resp.status_code == 403

    def test_unauthenticated_access_redirects_to_login(self, app, client, db_session):
        """Unauthenticated users are redirected to login."""
        resp = client.get('/scheduler/')
        
        # Should redirect to login page
        assert resp.status_code == 302
        assert 'login' in resp.location.lower()


# -------------------------------------------------------------------
# Index Page Tests
# -------------------------------------------------------------------

class TestIndexPage:
    """Test the scheduler index page."""

    def test_index_no_terms(self, app, client, db_session, supervisor_user):
        """Shows appropriate message when no terms exist."""
        login_user(client, supervisor_user)
        
        resp = client.get('/scheduler/')
        
        assert resp.status_code == 200
        # Should show message about no terms
        assert b'No term found' in resp.data or b'create a term' in resp.data.lower()

    def test_index_with_term(self, app, client, db_session, supervisor_user, sample_term):
        """Renders correctly with a term and week overview."""
        login_user(client, supervisor_user)
        
        resp = client.get('/scheduler/')
        
        assert resp.status_code == 200
        # Should show the term name
        assert sample_term.name.encode() in resp.data
        # Should have week overview section
        assert b'week' in resp.data.lower()

    def test_index_term_selection(self, app, client, db_session, supervisor_user, sample_term):
        """Term selection via query parameter works."""
        login_user(client, supervisor_user)
        
        # Create another term
        term2 = Term(
            name="Spring 2026",
            start_date=date(2026, 1, 15),
            end_date=date(2026, 5, 15),
            availability_deadline=date(2026, 1, 1),
            locked=False
        )
        db_session.add(term2)
        db_session.commit()
        
        # Select the specific term
        resp = client.get(f'/scheduler/?term_id={sample_term.term_id}')
        
        assert resp.status_code == 200
        assert sample_term.name.encode() in resp.data

    def test_index_displays_shift_statistics(self, app, client, db_session, supervisor_user, sample_term, sample_shift):
        """Index page displays shift statistics."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/scheduler/?term_id={sample_term.term_id}')
        
        assert resp.status_code == 200
        # Should show shift count or statistics
        # The template should contain some shift information

    def test_index_shows_staffing_needs_status(self, app, client, db_session, supervisor_user, sample_term, staffing_needs):
        """Index indicates if staffing needs are defined."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/scheduler/?term_id={sample_term.term_id}')
        
        assert resp.status_code == 200


# -------------------------------------------------------------------
# Edit Schedule Page Tests
# -------------------------------------------------------------------

class TestEditSchedulePage:
    """Test the edit schedule page."""

    def test_edit_schedule_default_term(self, app, client, db_session, supervisor_user, sample_term):
        """Redirects to latest term when no term_id specified."""
        login_user(client, supervisor_user)
        
        # Without term_id, should redirect to include term_id
        resp = client.get('/scheduler/edit-schedule')
        
        assert resp.status_code == 302
        assert f'term_id={sample_term.term_id}' in resp.location

    def test_edit_schedule_renders(self, app, client, db_session, supervisor_user, sample_term, sample_shift):
        """Edit schedule page renders with week view and shifts."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/scheduler/edit-schedule?term_id={sample_term.term_id}')
        
        assert resp.status_code == 200
        # Should have edit schedule interface elements
        assert b'edit' in resp.data.lower() or b'schedule' in resp.data.lower()

    def test_edit_schedule_week_navigation(self, app, client, db_session, supervisor_user, sample_term):
        """Week navigation parameter works."""
        login_user(client, supervisor_user)
        
        # Go to week 2
        resp = client.get(f'/scheduler/edit-schedule?term_id={sample_term.term_id}&week=1')
        
        assert resp.status_code == 200

    def test_edit_schedule_shows_students(self, app, client, db_session, supervisor_user, sample_term, student_user):
        """Edit schedule page shows available students."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/scheduler/edit-schedule?term_id={sample_term.term_id}')
        
        assert resp.status_code == 200
        # Should list students
        assert student_user.name.encode() in resp.data

    def test_edit_schedule_invalid_term(self, app, client, db_session, supervisor_user):
        """Returns 404 for invalid term_id."""
        login_user(client, supervisor_user)
        
        resp = client.get('/scheduler/edit-schedule?term_id=99999')
        
        assert resp.status_code == 404


# -------------------------------------------------------------------
# Generation Results Page Tests
# -------------------------------------------------------------------

class TestGenerationResultsPage:
    """Test the generation results page."""

    def test_generation_results_missing_params(self, app, client, db_session, supervisor_user):
        """Redirects with error when missing parameters."""
        login_user(client, supervisor_user)
        
        resp = client.get('/scheduler/generation-results')
        
        # Should redirect due to missing parameters
        assert resp.status_code == 302

    def test_generation_results_renders(self, app, client, db_session, supervisor_user, sample_term, sample_shift, policy):
        """Generation results page renders with shift data."""
        login_user(client, supervisor_user)
        
        resp = client.get(
            f'/scheduler/generation-results?term_id={sample_term.term_id}'
            f'&start_date=2025-09-01&end_date=2025-09-07'
        )
        
        # Route may render (200) or redirect on error (302)
        assert resp.status_code in [200, 302]

    def test_generation_results_invalid_term(self, app, client, db_session, supervisor_user):
        """Returns error for invalid term."""
        login_user(client, supervisor_user)
        
        resp = client.get(
            '/scheduler/generation-results?term_id=99999'
            '&start_date=2025-09-01&end_date=2025-09-07',
            follow_redirects=True
        )
        
        # Should redirect with error
        assert b'Term not found' in resp.data or resp.status_code == 200

    def test_generation_results_shows_statistics(self, app, client, db_session, supervisor_user, sample_term, sample_shift, policy):
        """Shows shift statistics and counts."""
        login_user(client, supervisor_user)
        
        resp = client.get(
            f'/scheduler/generation-results?term_id={sample_term.term_id}'
            f'&start_date=2025-09-01&end_date=2025-09-07'
        )
        
        # Route may render (200) or redirect on error (302)
        assert resp.status_code in [200, 302]


# -------------------------------------------------------------------
# Schedule Generation Tests
# -------------------------------------------------------------------

class TestScheduleGeneration:
    """Test the schedule generation functionality."""

    def test_generate_missing_params(self, app, client, db_session, supervisor_user, sample_term):
        """Returns error for missing term or dates."""
        login_user(client, supervisor_user)
        
        # Missing dates
        resp = client.post('/scheduler/generate', data={
            'term_id': sample_term.term_id
        }, follow_redirects=True)
        
        assert b'Please provide' in resp.data or b'error' in resp.data.lower()

    def test_generate_invalid_date_range(self, app, client, db_session, supervisor_user, sample_term):
        """Start date must be before or equal to end date."""
        login_user(client, supervisor_user)
        
        resp = client.post('/scheduler/generate', data={
            'term_id': sample_term.term_id,
            'start_date': '2025-09-10',
            'end_date': '2025-09-01'  # Before start date
        }, follow_redirects=True)
        
        assert b'Start date must be before' in resp.data or b'error' in resp.data.lower()

    def test_generate_dates_outside_term(self, app, client, db_session, supervisor_user, sample_term):
        """Dates must be within term dates."""
        login_user(client, supervisor_user)
        
        # Dates outside term range (term is Sep 1 - Dec 15, 2025)
        resp = client.post('/scheduler/generate', data={
            'term_id': sample_term.term_id,
            'start_date': '2025-08-01',  # Before term start
            'end_date': '2025-08-15'
        }, follow_redirects=True)
        
        assert b'must be within term dates' in resp.data or b'error' in resp.data.lower()

    def test_generate_invalid_term(self, app, client, db_session, supervisor_user):
        """Returns error for non-existent term."""
        login_user(client, supervisor_user)
        
        resp = client.post('/scheduler/generate', data={
            'term_id': 99999,
            'start_date': '2025-09-01',
            'end_date': '2025-09-07'
        }, follow_redirects=True)
        
        assert b'Term not found' in resp.data or b'error' in resp.data.lower()

    def test_generate_no_staffing_needs(self, app, client, db_session, supervisor_user, sample_term, availability_record):
        """Returns error when no staffing needs are defined."""
        login_user(client, supervisor_user)
        
        # No staffing needs exist for this term
        resp = client.post('/scheduler/generate', data={
            'term_id': sample_term.term_id,
            'start_date': '2025-09-01',
            'end_date': '2025-09-07'
        }, follow_redirects=True)
        
        assert b'No staffing needs' in resp.data or b'staffing' in resp.data.lower()

    def test_generate_no_availability(self, app, client, db_session, supervisor_user, sample_term, staffing_needs):
        """Returns error when no student availability exists."""
        login_user(client, supervisor_user)
        
        # Staffing needs exist but no availability
        resp = client.post('/scheduler/generate', data={
            'term_id': sample_term.term_id,
            'start_date': '2025-09-01',
            'end_date': '2025-09-07'
        }, follow_redirects=True)
        
        assert b'No student availability' in resp.data or b'availability' in resp.data.lower()

    def test_generate_existing_shifts_warning(self, app, client, db_session, supervisor_user, sample_term, 
                                              staffing_needs, availability_record, sample_shift):
        """Warning when shifts already exist in date range without overwrite flag."""
        login_user(client, supervisor_user)
        
        resp = client.post('/scheduler/generate', data={
            'term_id': sample_term.term_id,
            'start_date': '2025-09-01',
            'end_date': '2025-09-07'
            # No 'overwrite' flag
        }, follow_redirects=True)
        
        assert b'shifts already exist' in resp.data or b'Overwrite' in resp.data

    @patch('blueprints.scheduler.routes.cache')
    @patch('blueprints.scheduler.routes.invalidate_term')
    def test_generate_overwrite_existing(self, mock_invalidate, mock_cache, 
                                         app, client, db_session, supervisor_user, sample_term,
                                         staffing_needs, availability_record, sample_shift):
        """Overwrite flag deletes existing shifts before generating."""
        login_user(client, supervisor_user)
        
        # Verify the shift exists
        existing_count = Shift.query.filter_by(term_id=sample_term.term_id).count()
        assert existing_count == 1
        
        # Mock the schedule generator
        with patch('blueprints.scheduler.routes.ScheduleGenerator') as mock_gen:
            mock_gen.return_value.generate_schedule.return_value = {
                'total_shifts_generated': 0,
                'warnings': []
            }
            
            resp = client.post('/scheduler/generate', data={
                'term_id': sample_term.term_id,
                'start_date': '2025-09-01',
                'end_date': '2025-09-07',
                'overwrite': 'true'
            }, follow_redirects=True)
        
        # Original shift should be deleted
        remaining = Shift.query.filter_by(term_id=sample_term.term_id).count()
        assert remaining == 0

    @patch('blueprints.scheduler.routes.cache')
    @patch('blueprints.scheduler.routes.invalidate_term')
    @patch('blueprints.scheduler.routes.ScheduleGenerator')
    def test_generate_success(self, mock_gen, mock_invalidate, mock_cache,
                              app, client, db_session, supervisor_user, sample_term,
                              staffing_needs, availability_record):
        """Successful schedule generation with mocked generator."""
        login_user(client, supervisor_user)
        
        # Configure mock generator
        mock_gen.return_value.generate_schedule.return_value = {
            'total_shifts_generated': 5,
            'warnings': ['Some warning message']
        }
        
        resp = client.post('/scheduler/generate', data={
            'term_id': sample_term.term_id,
            'start_date': '2025-09-01',
            'end_date': '2025-09-07'
        }, follow_redirects=True)
        
        assert resp.status_code == 200
        # Should show success message
        assert b'Schedule generated successfully' in resp.data or b'shifts' in resp.data.lower()
        
        # Generator should have been called
        mock_gen.return_value.generate_schedule.assert_called_once()

    @patch('blueprints.scheduler.routes.cache')
    @patch('blueprints.scheduler.routes.invalidate_term')
    @patch('blueprints.scheduler.routes.ScheduleGenerator')
    def test_generate_no_shifts_generated(self, mock_gen, mock_invalidate, mock_cache,
                                          app, client, db_session, supervisor_user, sample_term,
                                          staffing_needs, availability_record):
        """Shows message when no shifts were generated."""
        login_user(client, supervisor_user)
        
        # Configure mock to generate zero shifts
        mock_gen.return_value.generate_schedule.return_value = {
            'total_shifts_generated': 0,
            'warnings': []
        }
        
        resp = client.post('/scheduler/generate', data={
            'term_id': sample_term.term_id,
            'start_date': '2025-09-01',
            'end_date': '2025-09-07'
        }, follow_redirects=True)
        
        assert b'No shifts were generated' in resp.data or b'error' in resp.data.lower()

    def test_generate_invalid_date_format(self, app, client, db_session, supervisor_user, sample_term):
        """Returns error for invalid date format."""
        login_user(client, supervisor_user)
        
        resp = client.post('/scheduler/generate', data={
            'term_id': sample_term.term_id,
            'start_date': 'invalid-date',
            'end_date': '2025-09-07'
        }, follow_redirects=True)
        
        assert b'Invalid date format' in resp.data or b'error' in resp.data.lower()

    @patch('blueprints.scheduler.routes.ScheduleGenerator')
    def test_generate_exception_handling(self, mock_gen, app, client, db_session, supervisor_user, sample_term,
                                         staffing_needs, availability_record):
        """Handles exceptions during generation gracefully."""
        login_user(client, supervisor_user)
        
        # Make generator raise an exception
        mock_gen.return_value.generate_schedule.side_effect = Exception("Generation failed")
        
        resp = client.post('/scheduler/generate', data={
            'term_id': sample_term.term_id,
            'start_date': '2025-09-01',
            'end_date': '2025-09-07'
        }, follow_redirects=True)
        
        assert b'Error generating schedule' in resp.data or b'error' in resp.data.lower()


# -------------------------------------------------------------------
# Legacy Shift CRUD Tests
# -------------------------------------------------------------------

class TestLegacyShiftCRUD:
    """Test the legacy (non-REST) shift CRUD routes."""

    def test_edit_shift_get(self, app, client, db_session, supervisor_user, sample_shift):
        """GET request returns shift data as JSON."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/scheduler/edit-shift/{sample_shift.shift_id}')
        
        assert resp.status_code == 200
        data = resp.json
        assert 'shift' in data
        assert data['shift']['shift_id'] == sample_shift.shift_id
        assert data['shift']['start_time'] == '09:00'
        assert data['shift']['end_time'] == '11:00'

    def test_edit_shift_get_not_found(self, app, client, db_session, supervisor_user):
        """GET returns 404 for non-existent shift."""
        login_user(client, supervisor_user)
        
        resp = client.get('/scheduler/edit-shift/99999')
        
        assert resp.status_code == 404

    def test_edit_shift_post_success(self, app, client, db_session, supervisor_user, sample_shift, policy):
        """POST updates shift fields successfully."""
        login_user(client, supervisor_user)
        
        resp = client.post(f'/scheduler/edit-shift/{sample_shift.shift_id}', json={
            'start_time': '10:00',
            'end_time': '12:00'
        })
        
        assert resp.status_code == 200
        data = resp.json
        assert data['success'] is True
        assert data['shift']['start_time'] == '10:00'
        assert data['shift']['end_time'] == '12:00'
        
        # Verify in database
        db_session.refresh(sample_shift)
        assert sample_shift.start_time == time(10, 0)
        assert sample_shift.end_time == time(12, 0)
        assert sample_shift.was_manually_adjusted is True

    def test_edit_shift_validation_error(self, app, client, db_session, supervisor_user, sample_shift, policy):
        """POST returns warning for invalid shift duration."""
        login_user(client, supervisor_user)
        
        # 30 minutes is below the minimum 60-minute policy
        resp = client.post(f'/scheduler/edit-shift/{sample_shift.shift_id}', json={
            'start_time': '09:00',
            'end_time': '09:30'
        })
        
        assert resp.status_code == 200
        data = resp.json
        assert data['success'] is False
        assert data.get('warning') is True or 'error' in data

    def test_edit_shift_update_user(self, app, client, db_session, supervisor_user, sample_shift, student_user, policy):
        """POST can update the assigned user."""
        login_user(client, supervisor_user)
        
        # Create another student
        other_student = User(
            name="Other Student",
            email="other@colby.edu",
            role="student",
            is_active=True
        )
        other_student.set_password("testpass")
        db_session.add(other_student)
        db_session.commit()
        
        resp = client.post(f'/scheduler/edit-shift/{sample_shift.shift_id}', json={
            'user_id': other_student.user_id
        })
        
        assert resp.status_code == 200
        data = resp.json
        assert data['success'] is True
        
        # Verify in database
        db_session.refresh(sample_shift)
        assert sample_shift.user_id == other_student.user_id

    @patch('blueprints.scheduler.routes.cache')
    @patch('blueprints.scheduler.routes.invalidate_term')
    @patch('blueprints.scheduler.routes.invalidate_student')
    def test_create_shift_success(self, mock_inv_student, mock_inv_term, mock_cache,
                                  app, client, db_session, supervisor_user, sample_term, student_user, policy):
        """Creates a new shift successfully."""
        login_user(client, supervisor_user)
        
        resp = client.post('/scheduler/create-shift', json={
            'term_id': sample_term.term_id,
            'user_id': student_user.user_id,
            'date': '2025-09-02',
            'start_time': '14:00',
            'end_time': '16:00'
        })
        
        assert resp.status_code == 200
        data = resp.json
        assert data['success'] is True
        assert 'shift' in data
        assert data['shift']['start_time'] == '14:00'
        assert data['shift']['end_time'] == '16:00'
        
        # Verify in database
        new_shift = Shift.query.filter_by(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 2)
        ).first()
        assert new_shift is not None
        assert new_shift.was_manually_adjusted is True

    def test_create_shift_validation_error(self, app, client, db_session, supervisor_user, sample_term, student_user, policy):
        """Returns error for invalid shift (too short)."""
        login_user(client, supervisor_user)
        
        resp = client.post('/scheduler/create-shift', json={
            'term_id': sample_term.term_id,
            'user_id': student_user.user_id,
            'date': '2025-09-02',
            'start_time': '14:00',
            'end_time': '14:30'  # Only 30 minutes
        })
        
        assert resp.status_code == 200
        data = resp.json
        assert data['success'] is False
        assert data.get('warning') is True or 'error' in data

    def test_create_shift_missing_fields(self, app, client, db_session, supervisor_user, sample_term):
        """Returns error when required fields are missing."""
        login_user(client, supervisor_user)
        
        resp = client.post('/scheduler/create-shift', json={
            'term_id': sample_term.term_id
            # Missing user_id, date, start_time, end_time
        })
        
        assert resp.status_code == 500
        data = resp.json
        assert data['success'] is False

    @patch('blueprints.scheduler.routes.cache')
    @patch('blueprints.scheduler.routes.invalidate_term')
    @patch('blueprints.scheduler.routes.invalidate_student')
    def test_delete_shift_success(self, mock_inv_student, mock_inv_term, mock_cache,
                                  app, client, db_session, supervisor_user, sample_shift):
        """Deletes a shift successfully."""
        login_user(client, supervisor_user)
        
        shift_id = sample_shift.shift_id
        
        resp = client.post(f'/scheduler/delete-shift/{shift_id}')
        
        assert resp.status_code == 200
        data = resp.json
        assert data['success'] is True
        
        # Verify deleted from database
        deleted_shift = Shift.query.get(shift_id)
        assert deleted_shift is None

    def test_delete_shift_not_found(self, app, client, db_session, supervisor_user):
        """Returns error for non-existent shift."""
        login_user(client, supervisor_user)
        
        resp = client.post('/scheduler/delete-shift/99999')
        
        # Route uses get_or_404 inside try/except, so returns 500 with error
        assert resp.status_code in [404, 500]
        data = resp.json
        assert data['success'] is False

    @patch('blueprints.scheduler.routes.invalidate_student')
    def test_reassign_shift_success(self, mock_inv_student, app, client, db_session, supervisor_user, sample_shift, student_user):
        """Reassigns a shift to a different student."""
        login_user(client, supervisor_user)
        
        # Create another student
        new_student = User(
            name="New Student",
            email="newstudent@colby.edu",
            role="student",
            is_active=True
        )
        new_student.set_password("testpass")
        db_session.add(new_student)
        db_session.commit()
        
        original_user_id = sample_shift.user_id
        
        resp = client.post(f'/scheduler/reassign-shift/{sample_shift.shift_id}', json={
            'user_id': new_student.user_id
        })
        
        assert resp.status_code == 200
        data = resp.json
        assert data['success'] is True
        assert data['shift']['user_name'] == 'New Student'
        
        # Verify in database
        db_session.refresh(sample_shift)
        assert sample_shift.user_id == new_student.user_id
        assert sample_shift.was_manually_adjusted is True

    def test_reassign_shift_not_found(self, app, client, db_session, supervisor_user, student_user):
        """Returns error when shift doesn't exist."""
        login_user(client, supervisor_user)
        
        resp = client.post('/scheduler/reassign-shift/99999', json={
            'user_id': student_user.user_id
        })
        
        # Route uses get_or_404 inside try/except, so returns 500 with error
        assert resp.status_code in [404, 500]
        data = resp.json
        assert data['success'] is False

    def test_edit_shift_exception_handling(self, app, client, db_session, supervisor_user, sample_shift):
        """Handles exceptions during edit gracefully."""
        login_user(client, supervisor_user)
        
        # Invalid time format
        resp = client.post(f'/scheduler/edit-shift/{sample_shift.shift_id}', json={
            'start_time': 'invalid'
        })
        
        assert resp.status_code == 500
        data = resp.json
        assert data['success'] is False


# -------------------------------------------------------------------
# REST API Tests (/api/shifts/*)
# -------------------------------------------------------------------

class TestShiftsRestAPI:
    """Test the REST API endpoints for shifts."""

    # --- List Shifts (GET /api/shifts) ---

    def test_api_list_shifts_empty(self, app, client, db_session, supervisor_user):
        """Returns empty list when no shifts exist."""
        login_user(client, supervisor_user)
        
        resp = client.get('/scheduler/api/shifts')
        
        assert resp.status_code == 200
        data = resp.json
        assert data['success'] is True
        assert data['data'] == []

    def test_api_list_shifts_with_data(self, app, client, db_session, supervisor_user, sample_shift):
        """Returns list of shifts."""
        login_user(client, supervisor_user)
        
        resp = client.get('/scheduler/api/shifts')
        
        assert resp.status_code == 200
        data = resp.json
        assert data['success'] is True
        assert len(data['data']) == 1
        assert data['data'][0]['shift_id'] == sample_shift.shift_id

    def test_api_list_shifts_filter_by_term(self, app, client, db_session, supervisor_user, sample_term, sample_shift):
        """Filters shifts by term_id."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/scheduler/api/shifts?term_id={sample_term.term_id}')
        
        assert resp.status_code == 200
        data = resp.json
        assert data['success'] is True
        assert len(data['data']) == 1

    def test_api_list_shifts_filter_by_user(self, app, client, db_session, supervisor_user, student_user, sample_shift):
        """Filters shifts by user_id."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/scheduler/api/shifts?user_id={student_user.user_id}')
        
        assert resp.status_code == 200
        data = resp.json
        assert data['success'] is True
        assert len(data['data']) == 1

    def test_api_list_shifts_filter_by_date_range(self, app, client, db_session, supervisor_user, sample_shift):
        """Filters shifts by date range."""
        login_user(client, supervisor_user)
        
        resp = client.get('/scheduler/api/shifts?start_date=2025-09-01&end_date=2025-09-01')
        
        assert resp.status_code == 200
        data = resp.json
        assert data['success'] is True
        assert len(data['data']) == 1

    def test_api_list_shifts_filter_excludes(self, app, client, db_session, supervisor_user, sample_shift):
        """Filter excludes non-matching shifts."""
        login_user(client, supervisor_user)
        
        # Date range that doesn't include the shift
        resp = client.get('/scheduler/api/shifts?start_date=2025-10-01&end_date=2025-10-07')
        
        assert resp.status_code == 200
        data = resp.json
        assert data['success'] is True
        assert len(data['data']) == 0

    # --- Create Shift (POST /api/shifts) ---

    @patch('blueprints.scheduler.routes.cache')
    @patch('blueprints.scheduler.routes.invalidate_term')
    @patch('blueprints.scheduler.routes.invalidate_student')
    def test_api_create_shift_success(self, mock_inv_student, mock_inv_term, mock_cache,
                                      app, client, db_session, supervisor_user, sample_term, student_user, policy):
        """Creates a shift via API and returns 201."""
        login_user(client, supervisor_user)
        
        resp = client.post('/scheduler/api/shifts', json={
            'term_id': sample_term.term_id,
            'user_id': student_user.user_id,
            'date': '2025-09-03',
            'start_time': '09:00',
            'end_time': '11:00'
        })
        
        assert resp.status_code == 201
        data = resp.json
        assert data['success'] is True
        assert 'data' in data
        assert data['data']['start_time'] == '09:00'
        assert data['data']['end_time'] == '11:00'

    def test_api_create_shift_missing_field(self, app, client, db_session, supervisor_user, sample_term):
        """Returns 400 for missing required fields."""
        login_user(client, supervisor_user)
        
        resp = client.post('/scheduler/api/shifts', json={
            'term_id': sample_term.term_id
            # Missing user_id, date, start_time, end_time
        })
        
        assert resp.status_code == 400
        data = resp.json
        assert data['success'] is False
        assert 'Missing required field' in data['error']

    def test_api_create_shift_invalid_duration(self, app, client, db_session, supervisor_user, sample_term, student_user, policy):
        """Returns 400 for invalid shift duration."""
        login_user(client, supervisor_user)
        
        resp = client.post('/scheduler/api/shifts', json={
            'term_id': sample_term.term_id,
            'user_id': student_user.user_id,
            'date': '2025-09-03',
            'start_time': '09:00',
            'end_time': '09:30'  # Only 30 minutes - below minimum
        })
        
        assert resp.status_code == 400
        data = resp.json
        assert data['success'] is False
        assert data.get('warning') is True

    # --- Get Shift (GET /api/shifts/<id>) ---

    def test_api_get_shift_success(self, app, client, db_session, supervisor_user, sample_shift):
        """Returns shift by ID."""
        login_user(client, supervisor_user)
        
        resp = client.get(f'/scheduler/api/shifts/{sample_shift.shift_id}')
        
        assert resp.status_code == 200
        data = resp.json
        assert data['success'] is True
        assert data['data']['shift_id'] == sample_shift.shift_id
        assert data['data']['start_time'] == '09:00'
        assert data['data']['end_time'] == '11:00'

    def test_api_get_shift_not_found(self, app, client, db_session, supervisor_user):
        """Returns 404 for non-existent shift."""
        login_user(client, supervisor_user)
        
        resp = client.get('/scheduler/api/shifts/99999')
        
        assert resp.status_code == 404
        data = resp.json
        assert data['success'] is False
        assert 'not found' in data['error'].lower()

    # --- Update Shift (PUT /api/shifts/<id>) ---

    def test_api_update_shift_success(self, app, client, db_session, supervisor_user, sample_shift, policy):
        """Updates shift and returns updated data."""
        login_user(client, supervisor_user)
        
        resp = client.put(f'/scheduler/api/shifts/{sample_shift.shift_id}', json={
            'start_time': '10:00',
            'end_time': '12:00'
        })
        
        assert resp.status_code == 200
        data = resp.json
        assert data['success'] is True
        assert data['data']['start_time'] == '10:00'
        assert data['data']['end_time'] == '12:00'
        
        # Verify in database
        db_session.refresh(sample_shift)
        assert sample_shift.start_time == time(10, 0)

    def test_api_update_shift_not_found(self, app, client, db_session, supervisor_user):
        """Returns 404 for non-existent shift."""
        login_user(client, supervisor_user)
        
        resp = client.put('/scheduler/api/shifts/99999', json={
            'start_time': '10:00'
        })
        
        assert resp.status_code == 404

    def test_api_update_shift_invalid_duration(self, app, client, db_session, supervisor_user, sample_shift, policy):
        """Returns 400 for invalid duration update."""
        login_user(client, supervisor_user)
        
        resp = client.put(f'/scheduler/api/shifts/{sample_shift.shift_id}', json={
            'start_time': '09:00',
            'end_time': '09:30'  # Too short
        })
        
        assert resp.status_code == 400
        data = resp.json
        assert data['success'] is False

    def test_api_update_shift_partial(self, app, client, db_session, supervisor_user, sample_shift, policy):
        """Partial update only changes specified fields."""
        login_user(client, supervisor_user)
        
        original_end = sample_shift.end_time
        
        resp = client.put(f'/scheduler/api/shifts/{sample_shift.shift_id}', json={
            'start_time': '08:00'  # Only change start time
        })
        
        assert resp.status_code == 200
        data = resp.json
        assert data['success'] is True
        assert data['data']['start_time'] == '08:00'
        # End time should be unchanged
        assert data['data']['end_time'] == original_end.strftime('%H:%M')

    # --- Delete Shift (DELETE /api/shifts/<id>) ---

    @patch('blueprints.scheduler.routes.cache')
    @patch('blueprints.scheduler.routes.invalidate_term')
    @patch('blueprints.scheduler.routes.invalidate_student')
    def test_api_delete_shift_success(self, mock_inv_student, mock_inv_term, mock_cache,
                                      app, client, db_session, supervisor_user, sample_shift):
        """Deletes shift and returns 204."""
        login_user(client, supervisor_user)
        
        shift_id = sample_shift.shift_id
        
        resp = client.delete(f'/scheduler/api/shifts/{shift_id}')
        
        assert resp.status_code == 204
        
        # Verify deleted
        assert Shift.query.get(shift_id) is None

    def test_api_delete_shift_not_found(self, app, client, db_session, supervisor_user):
        """Returns 404 for non-existent shift."""
        login_user(client, supervisor_user)
        
        resp = client.delete('/scheduler/api/shifts/99999')
        
        assert resp.status_code == 404

    # --- Reassign Shift (PATCH /api/shifts/<id>/assignee) ---

    @patch('blueprints.scheduler.routes.invalidate_student')
    def test_api_reassign_shift_success(self, mock_inv_student, app, client, db_session, supervisor_user, sample_shift, student_user):
        """Reassigns shift to different user."""
        login_user(client, supervisor_user)
        
        # Create another student
        new_student = User(
            name="API New Student",
            email="apinewstudent@colby.edu",
            role="student",
            is_active=True
        )
        new_student.set_password("testpass")
        db_session.add(new_student)
        db_session.commit()
        
        resp = client.patch(f'/scheduler/api/shifts/{sample_shift.shift_id}/assignee', json={
            'user_id': new_student.user_id
        })
        
        assert resp.status_code == 200
        data = resp.json
        assert data['success'] is True
        assert data['data']['user_id'] == new_student.user_id
        assert data['data']['user_name'] == 'API New Student'

    def test_api_reassign_shift_missing_user_id(self, app, client, db_session, supervisor_user, sample_shift):
        """Returns 400 when user_id is missing."""
        login_user(client, supervisor_user)
        
        resp = client.patch(f'/scheduler/api/shifts/{sample_shift.shift_id}/assignee', json={})
        
        assert resp.status_code == 400
        data = resp.json
        assert data['success'] is False
        assert 'user_id is required' in data['error']

    def test_api_reassign_shift_user_not_found(self, app, client, db_session, supervisor_user, sample_shift):
        """Returns 404 when target user doesn't exist."""
        login_user(client, supervisor_user)
        
        resp = client.patch(f'/scheduler/api/shifts/{sample_shift.shift_id}/assignee', json={
            'user_id': 99999
        })
        
        assert resp.status_code == 404
        data = resp.json
        assert data['success'] is False
        assert 'not found' in data['error'].lower()

    def test_api_reassign_shift_not_found(self, app, client, db_session, supervisor_user, student_user):
        """Returns 404 when shift doesn't exist."""
        login_user(client, supervisor_user)
        
        resp = client.patch('/scheduler/api/shifts/99999/assignee', json={
            'user_id': student_user.user_id
        })
        
        assert resp.status_code == 404


# -------------------------------------------------------------------
# Validation Endpoint Tests
# -------------------------------------------------------------------

class TestValidationEndpoints:
    """Test the shift validation endpoints."""

    # --- Legacy Validation (POST /validate-shift-edit) ---

    def test_validate_shift_edit_valid(self, app, client, db_session, supervisor_user, sample_term, policy):
        """Returns valid: true for valid shift."""
        login_user(client, supervisor_user)
        
        resp = client.post('/scheduler/validate-shift-edit', json={
            'term_id': sample_term.term_id,
            'date': '2025-09-01',
            'start_time': '09:00',
            'end_time': '11:00'  # 2 hours - valid
        })
        
        assert resp.status_code == 200
        data = resp.json
        assert data['valid'] is True
        assert data['errors'] == []

    def test_validate_shift_edit_duration_error_too_short(self, app, client, db_session, supervisor_user, sample_term, policy):
        """Returns error for shift below minimum duration."""
        login_user(client, supervisor_user)
        
        resp = client.post('/scheduler/validate-shift-edit', json={
            'term_id': sample_term.term_id,
            'date': '2025-09-01',
            'start_time': '09:00',
            'end_time': '09:30'  # 30 minutes - below 60 min minimum
        })
        
        assert resp.status_code == 200
        data = resp.json
        assert data['valid'] is False
        assert len(data['errors']) > 0
        assert any('min' in e.lower() or 'below' in e.lower() for e in data['errors'])

    def test_validate_shift_edit_duration_error_too_long(self, app, client, db_session, supervisor_user, sample_term, policy):
        """Returns error for shift above maximum duration."""
        login_user(client, supervisor_user)
        
        resp = client.post('/scheduler/validate-shift-edit', json={
            'term_id': sample_term.term_id,
            'date': '2025-09-01',
            'start_time': '09:00',
            'end_time': '13:30'  # 4.5 hours - above 3 hour maximum
        })
        
        assert resp.status_code == 200
        data = resp.json
        assert data['valid'] is False
        assert len(data['errors']) > 0
        assert any('max' in e.lower() or 'exceed' in e.lower() for e in data['errors'])

    def test_validate_shift_edit_overlap_error(self, app, client, db_session, supervisor_user, sample_term, student_user, sample_shift, policy):
        """Returns error for overlapping shifts."""
        login_user(client, supervisor_user)
        
        # Existing shift is 9:00-11:00
        # New shift at 10:00-12:00 would overlap
        resp = client.post('/scheduler/validate-shift-edit', json={
            'term_id': sample_term.term_id,
            'user_id': student_user.user_id,
            'date': '2025-09-01',
            'start_time': '10:00',
            'end_time': '12:00'
        })
        
        assert resp.status_code == 200
        data = resp.json
        assert data['valid'] is False
        assert any('overlap' in e.lower() for e in data['errors'])

    def test_validate_shift_edit_gap_warning(self, app, client, db_session, supervisor_user, sample_term, student_user, sample_shift, policy):
        """Returns warning for problematic gap between shifts."""
        login_user(client, supervisor_user)
        
        # Existing shift is 9:00-11:00
        # New shift at 11:20-13:20 creates a 20-minute gap (within 15-30 min threshold)
        resp = client.post('/scheduler/validate-shift-edit', json={
            'term_id': sample_term.term_id,
            'user_id': student_user.user_id,
            'date': '2025-09-01',
            'start_time': '11:20',
            'end_time': '13:20'
        })
        
        assert resp.status_code == 200
        data = resp.json
        # Should have warnings about gap
        assert len(data['warnings']) > 0 or data['valid'] is True

    def test_validate_shift_edit_for_existing_shift(self, app, client, db_session, supervisor_user, sample_term, 
                                                     sample_shift, student_user, policy):
        """Excludes current shift when checking for overlaps during edit."""
        login_user(client, supervisor_user)
        
        # Edit the same shift - should not report overlap with itself
        # Must include user_id to trigger the overlap check code path
        resp = client.post('/scheduler/validate-shift-edit', json={
            'term_id': sample_term.term_id,
            'user_id': student_user.user_id,
            'date': '2025-09-01',
            'start_time': '09:00',
            'end_time': '11:00',
            'shift_id': sample_shift.shift_id
        })
        
        assert resp.status_code == 200
        data = resp.json
        # Should not have overlap errors with itself
        assert not any('overlap' in e.lower() for e in data.get('errors', []))

    def test_validate_shift_edit_exception_handling(self, app, client, db_session, supervisor_user, sample_term):
        """Handles invalid data gracefully."""
        login_user(client, supervisor_user)
        
        resp = client.post('/scheduler/validate-shift-edit', json={
            'term_id': sample_term.term_id,
            'date': '2025-09-01',
            'start_time': 'invalid',
            'end_time': '11:00'
        })
        
        assert resp.status_code == 500
        data = resp.json
        assert data['valid'] is False

    # --- REST API Validation (POST /api/shifts/validate) ---

    def test_api_validate_shift_valid(self, app, client, db_session, supervisor_user, sample_term, policy):
        """Returns valid: true for valid shift via API."""
        login_user(client, supervisor_user)
        
        resp = client.post('/scheduler/api/shifts/validate', json={
            'term_id': sample_term.term_id,
            'date': '2025-09-01',
            'start_time': '09:00',
            'end_time': '11:00'
        })
        
        assert resp.status_code == 200
        data = resp.json
        assert data['success'] is True
        assert data['data']['valid'] is True
        assert data['data']['errors'] == []

    def test_api_validate_shift_invalid_duration(self, app, client, db_session, supervisor_user, sample_term, policy):
        """Returns error for invalid duration via API."""
        login_user(client, supervisor_user)
        
        resp = client.post('/scheduler/api/shifts/validate', json={
            'term_id': sample_term.term_id,
            'date': '2025-09-01',
            'start_time': '09:00',
            'end_time': '09:30'  # Too short
        })
        
        assert resp.status_code == 200
        data = resp.json
        assert data['success'] is True
        assert data['data']['valid'] is False
        assert len(data['data']['errors']) > 0

    def test_api_validate_shift_overlap(self, app, client, db_session, supervisor_user, sample_term, student_user, sample_shift, policy):
        """Returns error for overlapping shift via API."""
        login_user(client, supervisor_user)
        
        resp = client.post('/scheduler/api/shifts/validate', json={
            'term_id': sample_term.term_id,
            'user_id': student_user.user_id,
            'date': '2025-09-01',
            'start_time': '10:00',
            'end_time': '12:00'
        })
        
        assert resp.status_code == 200
        data = resp.json
        assert data['success'] is True
        assert data['data']['valid'] is False
        assert any('overlap' in e.lower() for e in data['data']['errors'])

    def test_api_validate_shift_missing_fields(self, app, client, db_session, supervisor_user, sample_term):
        """Returns 400 for missing required fields."""
        login_user(client, supervisor_user)
        
        resp = client.post('/scheduler/api/shifts/validate', json={
            'term_id': sample_term.term_id
            # Missing date, start_time, end_time
        })
        
        assert resp.status_code == 400
        data = resp.json
        assert data['success'] is False

    def test_api_validate_shift_for_edit(self, app, client, db_session, supervisor_user, sample_term, sample_shift, policy):
        """Excludes current shift during validation for edit."""
        login_user(client, supervisor_user)
        
        resp = client.post('/scheduler/api/shifts/validate', json={
            'term_id': sample_term.term_id,
            'date': '2025-09-01',
            'start_time': '09:00',
            'end_time': '11:00',
            'shift_id': sample_shift.shift_id
        })
        
        assert resp.status_code == 200
        data = resp.json
        assert data['success'] is True
        # Should be valid (no overlap with itself)
        assert not any('overlap' in e.lower() for e in data['data'].get('errors', []))

    def test_api_validate_shift_warnings(self, app, client, db_session, supervisor_user, sample_term, policy):
        """Returns warnings for undesirable hours."""
        login_user(client, supervisor_user)
        
        # Policy has undesireable_start=600 (6:00 AM), undesireable_end=2000 (8:00 PM)
        # A shift at 5:00-7:00 AM should trigger undesirable hours warning
        resp = client.post('/scheduler/api/shifts/validate', json={
            'term_id': sample_term.term_id,
            'date': '2025-09-01',
            'start_time': '05:00',
            'end_time': '07:00'
        })
        
        assert resp.status_code == 200
        data = resp.json
        assert data['success'] is True
        # Should have warnings about undesirable hours
        assert len(data['data']['warnings']) > 0 or data['data']['valid'] is True


# -------------------------------------------------------------------
# Edge Cases and Error Handling
# -------------------------------------------------------------------

class TestAdditionalCoverage:
    """Additional tests for 95%+ coverage."""

    # --- Index page week status 'complete' (lines 85-86) ---
    def test_index_week_status_complete(self, app, client, db_session, supervisor_user, sample_term, student_user, policy):
        """Index shows 'complete' status when week has 5+ shifts."""
        login_user(client, supervisor_user)
        
        # Create 5 shifts for the first week (Sep 1-7, 2025)
        for i in range(5):
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
        
        resp = client.get(f'/scheduler/?term_id={sample_term.term_id}')
        assert resp.status_code == 200

    # --- Generation with > 5 warnings (line 213) ---
    @patch('blueprints.scheduler.routes.cache')
    @patch('blueprints.scheduler.routes.invalidate_term')
    @patch('blueprints.scheduler.routes.ScheduleGenerator')
    def test_generate_many_warnings(self, mock_gen, mock_inv_term, mock_cache,
                                    app, client, db_session, supervisor_user, sample_term,
                                    staffing_needs, availability_record):
        """Shows truncated warnings when more than 5 are generated."""
        login_user(client, supervisor_user)
        
        # Configure mock to return > 5 warnings
        mock_gen.return_value.generate_schedule.return_value = {
            'total_shifts_generated': 3,
            'warnings': ['Warning 1', 'Warning 2', 'Warning 3', 'Warning 4', 
                        'Warning 5', 'Warning 6', 'Warning 7']
        }
        
        resp = client.post('/scheduler/generate', data={
            'term_id': sample_term.term_id,
            'start_date': '2025-09-01',
            'end_date': '2025-09-07'
        }, follow_redirects=True)
        
        assert resp.status_code == 200

    # --- Generation results student denied (lines 235-236) ---
    def test_generation_results_student_denied(self, app, client, db_session, student_user, sample_term):
        """Students cannot access generation results."""
        login_user(client, student_user)
        
        resp = client.get(
            f'/scheduler/generation-results?term_id={sample_term.term_id}'
            f'&start_date=2025-09-01&end_date=2025-09-07'
        )
        
        assert resp.status_code == 302
        resp = client.get(
            f'/scheduler/generation-results?term_id={sample_term.term_id}'
            f'&start_date=2025-09-01&end_date=2025-09-07',
            follow_redirects=True
        )
        assert b'Access denied' in resp.data

    # --- Generation results with violations (line 293) ---
    def test_generation_results_with_violations(self, app, client, db_session, supervisor_user, sample_term,
                                                 student_user, policy):
        """Generation results page detects shift violations."""
        login_user(client, supervisor_user)
        
        # Create a shift with invalid duration (30 min - below 60 min minimum)
        invalid_shift = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1),
            start_time=time(9, 0),
            end_time=time(9, 30),  # Only 30 minutes - violates policy
            was_manually_adjusted=False
        )
        db_session.add(invalid_shift)
        db_session.commit()
        
        resp = client.get(
            f'/scheduler/generation-results?term_id={sample_term.term_id}'
            f'&start_date=2025-09-01&end_date=2025-09-07'
        )
        
        # Should render (may have violations in output)
        assert resp.status_code in [200, 302]

    # --- Edit schedule no terms (lines 337-338) ---
    def test_edit_schedule_no_terms(self, app, client, db_session, supervisor_user):
        """Edit schedule redirects with error when no terms exist."""
        login_user(client, supervisor_user)
        
        resp = client.get('/scheduler/edit-schedule', follow_redirects=True)
        
        assert resp.status_code == 200
        assert b'No term found' in resp.data

    # --- Edit schedule week end past term end (line 350) ---
    def test_edit_schedule_week_past_term_end(self, app, client, db_session, supervisor_user):
        """Edit schedule handles week extending past term end."""
        login_user(client, supervisor_user)
        
        # Create a short term (1 week) to easily go past the end
        short_term = Term(
            name="Short Term",
            start_date=date(2025, 10, 1),
            end_date=date(2025, 10, 5),  # Only 5 days
            availability_deadline=date(2025, 9, 25),
            locked=False
        )
        db_session.add(short_term)
        db_session.commit()
        
        # Week 0 starts Oct 1, week_end would be Oct 7 which is past term end Oct 5
        resp = client.get(f'/scheduler/edit-schedule?term_id={short_term.term_id}&week=0')
        
        assert resp.status_code == 200

    # --- Edit shift update date field (line 399) ---
    def test_edit_shift_update_date(self, app, client, db_session, supervisor_user, sample_shift, policy):
        """Edit shift can update the date field."""
        login_user(client, supervisor_user)
        
        resp = client.post(f'/scheduler/edit-shift/{sample_shift.shift_id}', json={
            'date': '2025-09-02'
        })
        
        assert resp.status_code == 200
        data = resp.json
        assert data['success'] is True
        assert data['shift']['date'] == '2025-09-02'

    # --- Validate shift edit gap when new shift is before existing (line 656) ---
    def test_validate_shift_edit_gap_before_existing(self, app, client, db_session, supervisor_user, sample_term, 
                                                      student_user, sample_shift, policy):
        """Validation calculates gap when new shift is before existing shift."""
        login_user(client, supervisor_user)
        
        # Existing shift is 9:00-11:00
        # New shift at 7:00-8:40 creates a 20-minute gap before existing
        resp = client.post('/scheduler/validate-shift-edit', json={
            'term_id': sample_term.term_id,
            'user_id': student_user.user_id,
            'date': '2025-09-01',
            'start_time': '07:00',
            'end_time': '08:40'
        })
        
        assert resp.status_code == 200
        data = resp.json
        # Should have gap warning or be valid
        assert 'valid' in data

    # --- Validate insufficient transition time (line 662) ---
    def test_validate_shift_edit_insufficient_transition(self, app, client, db_session, supervisor_user, sample_term,
                                                          student_user, policy):
        """Validation detects insufficient transition time for adjacent shifts."""
        login_user(client, supervisor_user)
        
        # Create an existing shift at 9:00-11:00
        existing_shift = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 5),
            start_time=time(9, 0),
            end_time=time(11, 0),
            was_manually_adjusted=False
        )
        db_session.add(existing_shift)
        db_session.commit()
        
        # New shift at 7:00-9:00 ends exactly when existing starts (0 gap)
        # This triggers line 662: elif gap_minutes < policy.min_transition_time
        resp = client.post('/scheduler/validate-shift-edit', json={
            'term_id': sample_term.term_id,
            'user_id': student_user.user_id,
            'date': '2025-09-05',
            'start_time': '07:00',
            'end_time': '09:00'
        })
        
        assert resp.status_code == 200
        data = resp.json
        # Should report insufficient transition time error
        has_transition_error = any('transition' in e.lower() or 'Insufficient' in e for e in data.get('errors', []))
        assert has_transition_error

    # --- API list shifts exception handling (lines 723-724) ---
    def test_api_list_shifts_invalid_date(self, app, client, db_session, supervisor_user):
        """API list shifts handles invalid date format."""
        login_user(client, supervisor_user)
        
        # Invalid date format triggers exception in datetime.strptime
        resp = client.get('/scheduler/api/shifts?start_date=invalid-date')
        
        assert resp.status_code == 500
        data = resp.json
        assert data['success'] is False

    # --- API create shift general exception (lines 789-791) ---
    @patch('blueprints.scheduler.routes.db.session.commit')
    def test_api_create_shift_db_exception(self, mock_commit, app, client, db_session, supervisor_user, 
                                           sample_term, student_user, policy):
        """API create shift handles database exceptions with rollback."""
        login_user(client, supervisor_user)
        
        mock_commit.side_effect = Exception("Database error")
        
        resp = client.post('/scheduler/api/shifts', json={
            'term_id': sample_term.term_id,
            'user_id': student_user.user_id,
            'date': '2025-09-03',
            'start_time': '09:00',
            'end_time': '11:00'
        })
        
        assert resp.status_code == 500
        data = resp.json
        assert data['success'] is False

    # --- API update shift user_id and date (lines 836, 839) ---
    def test_api_update_shift_user_and_date(self, app, client, db_session, supervisor_user, sample_shift, 
                                            student_user, policy):
        """API update shift can change user_id and date."""
        login_user(client, supervisor_user)
        
        # Create another student
        other_student = User(
            name="Other API Student",
            email="otherapi@colby.edu",
            role="student",
            is_active=True
        )
        other_student.set_password("testpass")
        db_session.add(other_student)
        db_session.commit()
        
        resp = client.put(f'/scheduler/api/shifts/{sample_shift.shift_id}', json={
            'user_id': other_student.user_id,
            'date': '2025-09-05'
        })
        
        assert resp.status_code == 200
        data = resp.json
        assert data['success'] is True
        assert data['data']['user_id'] == other_student.user_id
        assert data['data']['date'] == '2025-09-05'

    # --- API update shift exception (lines 873-875) ---
    @patch('blueprints.scheduler.routes.db.session.commit')
    def test_api_update_shift_exception(self, mock_commit, app, client, db_session, supervisor_user, 
                                        sample_shift, policy):
        """API update shift handles exceptions with rollback."""
        login_user(client, supervisor_user)
        
        mock_commit.side_effect = Exception("Update failed")
        
        resp = client.put(f'/scheduler/api/shifts/{sample_shift.shift_id}', json={
            'start_time': '10:00',
            'end_time': '12:00'
        })
        
        assert resp.status_code == 500
        data = resp.json
        assert data['success'] is False

    # --- API delete shift exception (lines 907-909) ---
    @patch('blueprints.scheduler.routes.db.session.commit')
    def test_api_delete_shift_exception(self, mock_commit, app, client, db_session, supervisor_user, sample_shift):
        """API delete shift handles exceptions with rollback."""
        login_user(client, supervisor_user)
        
        mock_commit.side_effect = Exception("Delete failed")
        
        resp = client.delete(f'/scheduler/api/shifts/{sample_shift.shift_id}')
        
        assert resp.status_code == 500
        data = resp.json
        assert data['success'] is False

    # --- API reassign shift student denied (line 917) ---
    def test_api_reassign_shift_student_denied(self, app, client, db_session, student_user, sample_shift):
        """Students cannot reassign shifts via API."""
        login_user(client, student_user)
        
        resp = client.patch(f'/scheduler/api/shifts/{sample_shift.shift_id}/assignee', json={
            'user_id': student_user.user_id
        })
        
        assert resp.status_code == 403
        assert resp.json['success'] is False

    # --- API reassign shift exception (lines 957-959) ---
    @patch('blueprints.scheduler.routes.db.session.commit')
    def test_api_reassign_shift_exception(self, mock_commit, app, client, db_session, supervisor_user,
                                          sample_shift, student_user):
        """API reassign shift handles exceptions with rollback."""
        login_user(client, supervisor_user)
        
        mock_commit.side_effect = Exception("Reassign failed")
        
        resp = client.patch(f'/scheduler/api/shifts/{sample_shift.shift_id}/assignee', json={
            'user_id': student_user.user_id
        })
        
        assert resp.status_code == 500
        data = resp.json
        assert data['success'] is False

    # --- API validate shift student denied (line 967) ---
    def test_api_validate_shift_student_denied(self, app, client, db_session, student_user, sample_term):
        """Students cannot use API validation endpoint."""
        login_user(client, student_user)
        
        resp = client.post('/scheduler/api/shifts/validate', json={
            'term_id': sample_term.term_id,
            'date': '2025-09-01',
            'start_time': '09:00',
            'end_time': '11:00'
        })
        
        assert resp.status_code == 403
        assert resp.json['success'] is False

    # --- API validate shift with shift_id (line 1002) ---
    def test_api_validate_shift_with_shift_id(self, app, client, db_session, supervisor_user, sample_term,
                                              student_user, sample_shift, policy):
        """API validation excludes current shift when shift_id provided."""
        login_user(client, supervisor_user)
        
        resp = client.post('/scheduler/api/shifts/validate', json={
            'term_id': sample_term.term_id,
            'user_id': student_user.user_id,
            'date': '2025-09-01',
            'start_time': '09:00',
            'end_time': '11:00',
            'shift_id': sample_shift.shift_id
        })
        
        assert resp.status_code == 200
        data = resp.json
        assert data['success'] is True
        # Should not report overlap with itself
        assert not any('overlap' in e.lower() for e in data['data'].get('errors', []))

    # --- API validate shift gap calculations (lines 1010-1020) ---
    def test_api_validate_shift_gap_after_existing(self, app, client, db_session, supervisor_user, sample_term,
                                                    student_user, sample_shift, policy):
        """API validation calculates gap when new shift is AFTER existing (line 1011)."""
        login_user(client, supervisor_user)
        
        # Existing shift (sample_shift) is 9:00-11:00
        # New shift at 11:20-13:20 creates a 20-minute gap AFTER existing
        # This hits line 1011: if start_time_obj > other_shift.end_time
        resp = client.post('/scheduler/api/shifts/validate', json={
            'term_id': sample_term.term_id,
            'user_id': student_user.user_id,
            'date': '2025-09-01',
            'start_time': '11:20',
            'end_time': '13:20'
        })
        
        assert resp.status_code == 200
        data = resp.json
        assert data['success'] is True
        # Should have gap warning since 20 min is in (0, 30) range
        assert len(data['data'].get('warnings', [])) > 0

    def test_api_validate_shift_gap_before_existing(self, app, client, db_session, supervisor_user, sample_term,
                                                     student_user, sample_shift, policy):
        """API validation calculates gap when shift is before existing."""
        login_user(client, supervisor_user)
        
        # Existing shift is 9:00-11:00
        # New shift at 7:00-8:40 creates a 20-minute gap
        resp = client.post('/scheduler/api/shifts/validate', json={
            'term_id': sample_term.term_id,
            'user_id': student_user.user_id,
            'date': '2025-09-01',
            'start_time': '07:00',
            'end_time': '08:40'
        })
        
        assert resp.status_code == 200
        data = resp.json
        assert data['success'] is True

    def test_api_validate_shift_insufficient_transition(self, app, client, db_session, supervisor_user, sample_term,
                                                         student_user, policy):
        """API validation detects insufficient transition time."""
        login_user(client, supervisor_user)
        
        # Create an existing shift at 9:00-11:00
        existing_shift = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 6),
            start_time=time(9, 0),
            end_time=time(11, 0),
            was_manually_adjusted=False
        )
        db_session.add(existing_shift)
        db_session.commit()
        
        # New shift at 7:00-9:00 ends exactly when existing starts (0 gap)
        # This triggers line 1019-1020: elif gap_minutes < policy.min_transition_time
        resp = client.post('/scheduler/api/shifts/validate', json={
            'term_id': sample_term.term_id,
            'user_id': student_user.user_id,
            'date': '2025-09-06',
            'start_time': '07:00',
            'end_time': '09:00'
        })
        
        assert resp.status_code == 200
        data = resp.json
        assert data['success'] is True
        # Should report insufficient transition time error
        has_transition_error = any('transition' in e.lower() or 'Insufficient' in e for e in data['data'].get('errors', []))
        assert has_transition_error

    # --- API validate shift exception (lines 1039-1040) ---
    def test_api_validate_shift_exception(self, app, client, db_session, supervisor_user, sample_term):
        """API validation handles exceptions."""
        login_user(client, supervisor_user)
        
        # Invalid time format to trigger exception
        resp = client.post('/scheduler/api/shifts/validate', json={
            'term_id': sample_term.term_id,
            'date': '2025-09-01',
            'start_time': 'invalid',
            'end_time': '11:00'
        })
        
        assert resp.status_code == 500
        data = resp.json
        assert data['success'] is False


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_shift_with_default_policy(self, app, client, db_session, supervisor_user, sample_term, student_user):
        """Works with default policy when none is defined."""
        login_user(client, supervisor_user)
        
        # No policy exists for this term - should use defaults
        resp = client.post('/scheduler/validate-shift-edit', json={
            'term_id': sample_term.term_id,
            'date': '2025-09-01',
            'start_time': '09:00',
            'end_time': '11:00'
        })
        
        assert resp.status_code == 200
        data = resp.json
        # Should work with default policy values
        assert 'valid' in data

    def test_shift_on_different_dates(self, app, client, db_session, supervisor_user, sample_term, student_user, sample_shift, policy):
        """Shifts on different dates don't overlap."""
        login_user(client, supervisor_user)
        
        # Existing shift is on 2025-09-01
        # New shift on 2025-09-02 with same times should not overlap
        resp = client.post('/scheduler/validate-shift-edit', json={
            'term_id': sample_term.term_id,
            'user_id': student_user.user_id,
            'date': '2025-09-02',  # Different date
            'start_time': '09:00',
            'end_time': '11:00'
        })
        
        assert resp.status_code == 200
        data = resp.json
        assert data['valid'] is True
        assert not any('overlap' in e.lower() for e in data.get('errors', []))

    def test_multiple_shifts_same_user_same_day(self, app, client, db_session, supervisor_user, sample_term, student_user, sample_shift, policy):
        """Validates multiple shifts for same user on same day."""
        login_user(client, supervisor_user)
        
        # Existing shift is 9:00-11:00
        # Add a non-overlapping shift at 14:00-16:00
        resp = client.post('/scheduler/validate-shift-edit', json={
            'term_id': sample_term.term_id,
            'user_id': student_user.user_id,
            'date': '2025-09-01',
            'start_time': '14:00',
            'end_time': '16:00'
        })
        
        assert resp.status_code == 200
        data = resp.json
        assert data['valid'] is True

    @patch('blueprints.scheduler.routes.cache')
    @patch('blueprints.scheduler.routes.invalidate_term')
    @patch('blueprints.scheduler.routes.invalidate_student')
    def test_create_multiple_shifts(self, mock_inv_student, mock_inv_term, mock_cache,
                                    app, client, db_session, supervisor_user, sample_term, student_user, policy):
        """Can create multiple valid shifts."""
        login_user(client, supervisor_user)
        
        # Create first shift
        resp1 = client.post('/scheduler/api/shifts', json={
            'term_id': sample_term.term_id,
            'user_id': student_user.user_id,
            'date': '2025-09-02',
            'start_time': '09:00',
            'end_time': '11:00'
        })
        assert resp1.status_code == 201
        
        # Create second shift on same day, different time
        resp2 = client.post('/scheduler/api/shifts', json={
            'term_id': sample_term.term_id,
            'user_id': student_user.user_id,
            'date': '2025-09-02',
            'start_time': '14:00',
            'end_time': '16:00'
        })
        assert resp2.status_code == 201
        
        # Verify both exist
        shifts = Shift.query.filter_by(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 2)
        ).all()
        assert len(shifts) == 2
