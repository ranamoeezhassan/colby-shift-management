"""
Comprehensive test coverage for staffing/routes.py
This file provides complete test coverage for all functionality in the staffing routes.
The tests are isolated from other modules and can be run independently.
"""
import pytest
import json
from datetime import datetime, time, date, timedelta
from unittest.mock import patch, MagicMock
from flask import url_for
from models import db, User, Term, StaffingNeeds, Availability


class TestStaffingRoutes:
    """Complete test coverage for staffing routes module."""

    @pytest.fixture
    def authenticated_client(self, client, sample_user):
        """Create an authenticated test client."""
        # Actually log in the user
        response = client.post('/login', data={
            'email': 'test@colby.edu',
            'password': 'testpass',
            'g-recaptcha-response': 'test'
        }, follow_redirects=True)
        return client

    @pytest.fixture
    def sample_term(self):
        """Create a sample term for testing."""
        term = Term(
            name='Test Term',
            start_date=date(2025, 1, 15),
            end_date=date(2025, 5, 15),
            availability_deadline=date(2025, 1, 10),
            locked=False
        )
        db.session.add(term)
        db.session.commit()
        return term

    @pytest.fixture
    def locked_term(self):
        """Create a locked term for testing."""
        term = Term(
            name='Locked Term',
            start_date=date(2025, 1, 15),
            end_date=date(2025, 5, 15),
            availability_deadline=date(2025, 1, 10),
            locked=True
        )
        db.session.add(term)
        db.session.commit()
        return term

    @pytest.fixture
    def sample_staffing_need(self, sample_term):
        """Create a sample staffing need for testing."""
        need = StaffingNeeds(
            term_id=sample_term.term_id,
            day_of_week=0,  # Monday
            start_time=time(9, 0),
            end_time=time(17, 0),
            role_required='student',
            required_count=2
        )
        db.session.add(need)
        db.session.commit()
        return need

    @pytest.fixture
    def sample_availability(self, sample_user, sample_term):
        """Create a sample availability for testing."""
        availability = Availability(
            user_id=sample_user.user_id,
            term_id=sample_term.term_id,
            day_of_week='Monday',
            start_time=time(8, 0),
            end_time=time(18, 0),
            is_exception=False
        )
        db.session.add(availability)
        db.session.commit()
        return availability

    @pytest.fixture
    def student_user(self):
        """Create a student user for testing."""
        user = User(
            name='Test Student',
            email='student@colby.edu',
            role='student',
            is_active=True
        )
        user.set_password('testpass')
        db.session.add(user)
        db.session.commit()
        return user

    @pytest.fixture
    def supervisor_user(self):
        """Create a supervisor user for testing."""
        user = User(
            name='Test Supervisor',
            email='supervisor@colby.edu',
            role='supervisor',
            is_active=True
        )
        user.set_password('testpass')
        db.session.add(user)
        db.session.commit()
        return user

    # ================= GET REQUEST TESTS =================

    def test_index_get_no_terms(self, authenticated_client):
        """Test GET request to staffing index with no terms."""
        response = authenticated_client.get('/staffing/')
        assert response.status_code == 200

    def test_index_get_with_terms(self, authenticated_client, sample_term, sample_staffing_need):
        """Test GET request to staffing index with existing terms and staffing needs."""
        response = authenticated_client.get('/staffing/')
        assert response.status_code == 200
        # Should contain term name and staffing data
        assert sample_term.name.encode() in response.data

    def test_index_get_with_selected_term(self, authenticated_client, sample_term):
        """Test GET request with specific term selected via query parameter."""
        response = authenticated_client.get(f'/staffing/?term_id={sample_term.term_id}')
        assert response.status_code == 200

    def test_index_get_with_invalid_term_id(self, authenticated_client, sample_term):
        """Test GET request with invalid term ID."""
        response = authenticated_client.get('/staffing/?term_id=99999')
        assert response.status_code == 200

    def test_index_get_exception_handling(self, authenticated_client, sample_term):
        """Test exception handling in GET request."""
        with patch('models.StaffingNeeds.query') as mock_query:
            mock_query.filter.side_effect = Exception('Database error')
            response = authenticated_client.get('/staffing/')
            assert response.status_code == 200

    # ================= CREATE TERM TESTS =================

    def test_create_term_success(self, authenticated_client):
        """Test successful term creation."""
        term_data = {
            'action': 'create_term',
            'term_name': 'Spring 2025',
            'start_date': '2025-03-01',
            'end_date': '2025-06-01',
            'availability_deadline': '2025-02-28'
        }
        response = authenticated_client.post('/staffing/', data=term_data, follow_redirects=True)
        assert response.status_code == 200
        
        # Verify term was created
        term = Term.query.filter_by(name='Spring 2025').first()
        assert term is not None
        assert term.start_date == date(2025, 3, 1)
        assert term.end_date == date(2025, 6, 1)
        assert term.availability_deadline == date(2025, 2, 28)

    def test_create_term_missing_fields(self, authenticated_client):
        """Test term creation with missing required fields."""
        term_data = {
            'action': 'create_term',
            'term_name': 'Incomplete Term',
            # Missing dates
        }
        response = authenticated_client.post('/staffing/', data=term_data, follow_redirects=True)
        assert response.status_code == 200

    def test_create_term_invalid_date_format(self, authenticated_client):
        """Test term creation with invalid date format."""
        term_data = {
            'action': 'create_term',
            'term_name': 'Invalid Date Term',
            'start_date': 'invalid-date',
            'end_date': '2025-06-01',
            'availability_deadline': '2025-02-28'
        }
        response = authenticated_client.post('/staffing/', data=term_data, follow_redirects=True)
        assert response.status_code == 200

    def test_create_term_name_too_long(self, authenticated_client):
        """Test term creation with name that's too long."""
        term_data = {
            'action': 'create_term',
            'term_name': 'A' * 51,  # 51 characters, exceeds limit
            'start_date': '2025-03-01',
            'end_date': '2025-06-01',
            'availability_deadline': '2025-02-28'
        }
        response = authenticated_client.post('/staffing/', data=term_data, follow_redirects=True)
        assert response.status_code == 200

    def test_create_term_invalid_date_range(self, authenticated_client):
        """Test term creation with start date after end date."""
        term_data = {
            'action': 'create_term',
            'term_name': 'Invalid Range Term',
            'start_date': '2025-06-01',
            'end_date': '2025-03-01',  # End before start
            'availability_deadline': '2025-02-28'
        }
        response = authenticated_client.post('/staffing/', data=term_data, follow_redirects=True)
        assert response.status_code == 200

    def test_create_term_invalid_deadline(self, authenticated_client):
        """Test term creation with availability deadline after start date."""
        term_data = {
            'action': 'create_term',
            'term_name': 'Invalid Deadline Term',
            'start_date': '2025-03-01',
            'end_date': '2025-06-01',
            'availability_deadline': '2025-03-15'  # After start date
        }
        response = authenticated_client.post('/staffing/', data=term_data, follow_redirects=True)
        assert response.status_code == 200

    def test_create_term_duplicate_name(self, authenticated_client, sample_term):
        """Test term creation with duplicate name."""
        term_data = {
            'action': 'create_term',
            'term_name': sample_term.name,  # Duplicate name
            'start_date': '2025-03-01',
            'end_date': '2025-06-01',
            'availability_deadline': '2025-02-28'
        }
        response = authenticated_client.post('/staffing/', data=term_data, follow_redirects=True)
        assert response.status_code == 200

    def test_create_term_database_exception(self, authenticated_client):
        """Test term creation with database exception."""
        with patch('models.db.session.add') as mock_add:
            mock_add.side_effect = Exception('Database error')
            term_data = {
                'action': 'create_term',
                'term_name': 'Exception Term',
                'start_date': '2025-03-01',
                'end_date': '2025-06-01',
                'availability_deadline': '2025-02-28'
            }
            response = authenticated_client.post('/staffing/', data=term_data, follow_redirects=True)
            assert response.status_code == 200

    # ================= TOGGLE TERM LOCK TESTS =================

    def test_toggle_term_lock_unlock_to_lock(self, authenticated_client, sample_term):
        """Test toggling term from unlocked to locked."""
        lock_data = {
            'action': 'toggle_term_lock',
            'term_id': str(sample_term.term_id)
        }
        response = authenticated_client.post('/staffing/', data=lock_data, follow_redirects=True)
        assert response.status_code == 200
        
        # Verify term is now locked
        db.session.refresh(sample_term)
        assert sample_term.locked is True

    def test_toggle_term_lock_lock_to_unlock(self, authenticated_client, locked_term):
        """Test toggling term from locked to unlocked."""
        lock_data = {
            'action': 'toggle_term_lock',
            'term_id': str(locked_term.term_id)
        }
        response = authenticated_client.post('/staffing/', data=lock_data, follow_redirects=True)
        assert response.status_code == 200
        
        # Verify term is now unlocked
        db.session.refresh(locked_term)
        assert locked_term.locked is False

    def test_toggle_term_lock_invalid_term_id(self, authenticated_client):
        """Test toggling lock with invalid term ID."""
        lock_data = {
            'action': 'toggle_term_lock',
            'term_id': '99999'
        }
        response = authenticated_client.post('/staffing/', data=lock_data, follow_redirects=True)
        assert response.status_code == 200

    def test_toggle_term_lock_non_numeric_id(self, authenticated_client):
        """Test toggling lock with non-numeric term ID."""
        lock_data = {
            'action': 'toggle_term_lock',
            'term_id': 'invalid'
        }
        response = authenticated_client.post('/staffing/', data=lock_data, follow_redirects=True)
        assert response.status_code == 200

    def test_toggle_term_lock_database_exception(self, authenticated_client, sample_term):
        """Test toggle term lock with database exception."""
        with patch('models.db.session.commit') as mock_commit:
            mock_commit.side_effect = Exception('Database error')
            lock_data = {
                'action': 'toggle_term_lock',
                'term_id': str(sample_term.term_id)
            }
            response = authenticated_client.post('/staffing/', data=lock_data, follow_redirects=True)
            assert response.status_code == 200

    # ================= ADD COVERAGE TESTS =================

    def test_add_coverage_success(self, authenticated_client, sample_term, student_user):
        """Test successful coverage requirement addition."""
        coverage_data = {
            'action': 'add_coverage',
            'term_id': str(sample_term.term_id),
            'day_of_week': '0',  # Monday
            'start_time': '09:00',
            'end_time': '17:00',
            'role_required': 'student',
            'required_count': '1'
        }
        response = authenticated_client.post('/staffing/', data=coverage_data, follow_redirects=True)
        assert response.status_code == 200
        
        # Verify coverage was created
        need = StaffingNeeds.query.filter_by(
            term_id=sample_term.term_id,
            day_of_week=0
        ).first()
        assert need is not None
        assert need.start_time == time(9, 0)
        assert need.end_time == time(17, 0)
        assert need.role_required == 'student'
        assert need.required_count == 1

    def test_add_coverage_no_term(self, authenticated_client):
        """Test adding coverage when no term exists."""
        coverage_data = {
            'action': 'add_coverage',
            'day_of_week': '0',
            'start_time': '09:00',
            'end_time': '17:00',
            'role_required': 'student',
            'required_count': '1'
        }
        response = authenticated_client.post('/staffing/', data=coverage_data, follow_redirects=True)
        assert response.status_code == 200

    def test_add_coverage_invalid_time_range(self, authenticated_client, sample_term):
        """Test adding coverage with start time after end time."""
        coverage_data = {
            'action': 'add_coverage',
            'term_id': str(sample_term.term_id),
            'day_of_week': '0',
            'start_time': '17:00',
            'end_time': '09:00',  # End before start
            'role_required': 'student',
            'required_count': '1'
        }
        response = authenticated_client.post('/staffing/', data=coverage_data, follow_redirects=True)
        assert response.status_code == 200

    def test_add_coverage_overlap_existing(self, authenticated_client, sample_term, sample_staffing_need):
        """Test adding coverage that overlaps with existing requirement."""
        coverage_data = {
            'action': 'add_coverage',
            'term_id': str(sample_term.term_id),
            'day_of_week': str(sample_staffing_need.day_of_week),
            'start_time': '10:00',  # Overlaps with existing 09:00-17:00
            'end_time': '18:00',
            'role_required': sample_staffing_need.role_required,
            'required_count': '1'
        }
        response = authenticated_client.post('/staffing/', data=coverage_data, follow_redirects=True)
        assert response.status_code == 200

    def test_add_coverage_exceeds_active_users(self, authenticated_client, sample_term):
        """Test adding coverage that requires more users than available."""
        coverage_data = {
            'action': 'add_coverage',
            'term_id': str(sample_term.term_id),
            'day_of_week': '0',
            'start_time': '09:00',
            'end_time': '17:00',
            'role_required': 'student',
            'required_count': '100'  # More than available users
        }
        response = authenticated_client.post('/staffing/', data=coverage_data, follow_redirects=True)
        assert response.status_code == 200

    def test_add_coverage_no_users_for_role(self, authenticated_client, sample_term):
        """Test adding coverage for role with no active users."""
        coverage_data = {
            'action': 'add_coverage',
            'term_id': str(sample_term.term_id),
            'day_of_week': '0',
            'start_time': '09:00',
            'end_time': '17:00',
            'role_required': 'manager',  # No active managers exist
            'required_count': '1'
        }
        response = authenticated_client.post('/staffing/', data=coverage_data, follow_redirects=True)
        assert response.status_code == 200

    def test_add_coverage_with_availability(self, authenticated_client, sample_term, student_user, sample_availability):
        """Test adding coverage with existing availability data."""
        coverage_data = {
            'action': 'add_coverage',
            'term_id': str(sample_term.term_id),
            'day_of_week': '0',
            'start_time': '09:00',
            'end_time': '17:00',
            'role_required': 'student',
            'required_count': '1'
        }
        response = authenticated_client.post('/staffing/', data=coverage_data, follow_redirects=True)
        assert response.status_code == 200

    def test_add_coverage_insufficient_availability(self, authenticated_client, sample_term, student_user):
        """Test adding coverage with insufficient availability."""
        # Create limited availability
        limited_availability = Availability(
            user_id=student_user.user_id,
            term_id=sample_term.term_id,
            day_of_week='Monday',
            start_time=time(10, 0),
            end_time=time(12, 0),  # Only 2 hours available
            is_exception=False
        )
        db.session.add(limited_availability)
        db.session.commit()

        coverage_data = {
            'action': 'add_coverage',
            'term_id': str(sample_term.term_id),
            'day_of_week': '0',
            'start_time': '09:00',
            'end_time': '17:00',  # Requires 8 hours
            'role_required': 'student',
            'required_count': '1'
        }
        response = authenticated_client.post('/staffing/', data=coverage_data, follow_redirects=True)
        assert response.status_code == 200

    def test_add_coverage_invalid_input_format(self, authenticated_client, sample_term):
        """Test adding coverage with invalid input format."""
        coverage_data = {
            'action': 'add_coverage',
            'term_id': str(sample_term.term_id),
            'day_of_week': 'invalid',  # Invalid day
            'start_time': '09:00',
            'end_time': '17:00',
            'role_required': 'student',
            'required_count': 'invalid'  # Invalid count
        }
        response = authenticated_client.post('/staffing/', data=coverage_data, follow_redirects=True)
        assert response.status_code == 200

    def test_add_coverage_database_exception(self, authenticated_client, sample_term, student_user):
        """Test adding coverage with database exception."""
        with patch('models.db.session.add') as mock_add:
            mock_add.side_effect = Exception('Database error')
            coverage_data = {
                'action': 'add_coverage',
                'term_id': str(sample_term.term_id),
                'day_of_week': '0',
                'start_time': '09:00',
                'end_time': '17:00',
                'role_required': 'student',
                'required_count': '1'
            }
            response = authenticated_client.post('/staffing/', data=coverage_data, follow_redirects=True)
            assert response.status_code == 200

    # ================= DELETE COVERAGE TESTS =================

    def test_delete_coverage_success(self, authenticated_client, sample_staffing_need):
        """Test successful deletion of coverage requirement."""
        delete_data = {
            'action': 'delete_coverage',
            'need_id': str(sample_staffing_need.need_id)
        }
        response = authenticated_client.post('/staffing/', data=delete_data, follow_redirects=True)
        assert response.status_code == 200
        
        # Verify coverage was deleted
        need = StaffingNeeds.query.get(sample_staffing_need.need_id)
        assert need is None

    def test_delete_coverage_nonexistent(self, authenticated_client):
        """Test deleting nonexistent coverage requirement."""
        delete_data = {
            'action': 'delete_coverage',
            'need_id': '99999'
        }
        response = authenticated_client.post('/staffing/', data=delete_data, follow_redirects=True)
        assert response.status_code == 200

    def test_delete_coverage_invalid_id(self, authenticated_client):
        """Test deleting coverage with invalid ID."""
        delete_data = {
            'action': 'delete_coverage',
            'need_id': 'invalid'
        }
        response = authenticated_client.post('/staffing/', data=delete_data, follow_redirects=True)
        assert response.status_code == 200

    def test_delete_coverage_database_exception(self, authenticated_client, sample_staffing_need):
        """Test deleting coverage with database exception."""
        with patch('models.db.session.delete') as mock_delete:
            mock_delete.side_effect = Exception('Database error')
            delete_data = {
                'action': 'delete_coverage',
                'need_id': str(sample_staffing_need.need_id)
            }
            response = authenticated_client.post('/staffing/', data=delete_data, follow_redirects=True)
            assert response.status_code == 200

    # ================= BULK TEMPLATE TESTS =================

    def test_bulk_template_standard_weekdays(self, authenticated_client, sample_term):
        """Test applying standard weekdays template."""
        template_data = {
            'action': 'bulk_template',
            'template_type': 'standard_weekdays'
        }
        response = authenticated_client.post('/staffing/', data=template_data, follow_redirects=True)
        assert response.status_code == 200
        
        # Verify Monday-Friday 9AM-5PM requirements were created
        weekday_needs = StaffingNeeds.query.filter(
            StaffingNeeds.term_id == sample_term.term_id,
            StaffingNeeds.day_of_week.in_([0, 1, 2, 3, 4])  # Mon-Fri
        ).all()
        assert len(weekday_needs) == 5
        
        for need in weekday_needs:
            assert need.start_time == time(9, 0)
            assert need.end_time == time(17, 0)
            assert need.role_required == 'student'
            assert need.required_count == 2

    def test_bulk_template_extended_hours(self, authenticated_client, sample_term):
        """Test applying extended hours template."""
        template_data = {
            'action': 'bulk_template',
            'template_type': 'extended_hours'
        }
        response = authenticated_client.post('/staffing/', data=template_data, follow_redirects=True)
        assert response.status_code == 200
        
        # Verify extended hours requirements were created
        extended_needs = StaffingNeeds.query.filter_by(term_id=sample_term.term_id).all()
        assert len(extended_needs) == 15  # 3 time blocks × 5 weekdays

    def test_bulk_template_no_term(self, authenticated_client):
        """Test applying template when no term exists."""
        # Delete all terms first
        Term.query.delete()
        db.session.commit()
        
        template_data = {
            'action': 'bulk_template',
            'template_type': 'standard_weekdays'
        }
        response = authenticated_client.post('/staffing/', data=template_data, follow_redirects=True)
        assert response.status_code == 200

    def test_bulk_template_existing_coverage(self, authenticated_client, sample_term, sample_staffing_need):
        """Test applying template with existing coverage (should not create duplicates)."""
        template_data = {
            'action': 'bulk_template',
            'template_type': 'standard_weekdays'
        }
        response = authenticated_client.post('/staffing/', data=template_data, follow_redirects=True)
        assert response.status_code == 200
        
        # Should not create duplicate for existing coverage
        monday_needs = StaffingNeeds.query.filter(
            StaffingNeeds.term_id == sample_term.term_id,
            StaffingNeeds.day_of_week == 0,
            StaffingNeeds.start_time == time(9, 0),
            StaffingNeeds.end_time == time(17, 0)
        ).all()
        assert len(monday_needs) == 1  # Should not duplicate

    def test_bulk_template_database_exception(self, authenticated_client, sample_term):
        """Test applying template with database exception."""
        with patch('models.db.session.add') as mock_add:
            mock_add.side_effect = Exception('Database error')
            template_data = {
                'action': 'bulk_template',
                'template_type': 'standard_weekdays'
            }
            response = authenticated_client.post('/staffing/', data=template_data, follow_redirects=True)
            assert response.status_code == 200

    # ================= CLEAR ALL TESTS =================

    def test_clear_all_success(self, authenticated_client, sample_term, sample_staffing_need):
        """Test successful clearing of all coverage requirements."""
        clear_data = {
            'action': 'clear_all'
        }
        response = authenticated_client.post('/staffing/', data=clear_data, follow_redirects=True)
        assert response.status_code == 200
        
        # Verify all coverage requirements were deleted
        remaining_needs = StaffingNeeds.query.filter_by(term_id=sample_term.term_id).all()
        assert len(remaining_needs) == 0

    def test_clear_all_no_term(self, authenticated_client):
        """Test clearing all when no term exists."""
        # Delete all terms first
        Term.query.delete()
        db.session.commit()
        
        clear_data = {
            'action': 'clear_all'
        }
        response = authenticated_client.post('/staffing/', data=clear_data, follow_redirects=True)
        assert response.status_code == 200

    def test_clear_all_database_exception(self, authenticated_client, sample_term, sample_staffing_need):
        """Test clearing all with database exception."""
        with patch('models.StaffingNeeds.query') as mock_query:
            mock_query.filter().delete.side_effect = Exception('Database error')
            clear_data = {
                'action': 'clear_all'
            }
            response = authenticated_client.post('/staffing/', data=clear_data, follow_redirects=True)
            assert response.status_code == 200

    # ================= UPDATE COVERAGE TESTS =================

    def test_update_coverage_success_redirect(self, authenticated_client, sample_staffing_need, student_user):
        """Test successful update of coverage requirement (redirect mode)."""
        update_data = {
            'action': 'update_coverage',
            'need_id': str(sample_staffing_need.need_id),
            'day_of_week': '1',  # Change to Tuesday
            'start_time': '10:00',
            'end_time': '16:00',
            'role_required': 'student',
            'required_count': '1'
        }
        response = authenticated_client.post('/staffing/', data=update_data, follow_redirects=True)
        assert response.status_code == 200
        
        # Verify coverage was updated
        db.session.refresh(sample_staffing_need)
        assert sample_staffing_need.day_of_week == 1
        assert sample_staffing_need.start_time == time(10, 0)
        assert sample_staffing_need.end_time == time(16, 0)
        assert sample_staffing_need.required_count == 1

    def test_update_coverage_success_json(self, authenticated_client, sample_staffing_need, student_user):
        """Test successful update of coverage requirement (JSON mode)."""
        update_data = {
            'action': 'update_coverage',
            'need_id': str(sample_staffing_need.need_id),
            'day_of_week': '1',
            'start_time': '10:00',
            'end_time': '16:00',
            'role_required': 'student',
            'required_count': '1',
            'fetch': '1'  # JSON mode
        }
        response = authenticated_client.post('/staffing/', data=update_data)
        assert response.status_code == 200
        
        # Verify JSON response
        data = response.get_json()
        assert data['ok'] is True
        assert data['need']['need_id'] == sample_staffing_need.need_id
        assert data['need']['day_of_week'] == 1

    def test_update_coverage_nonexistent_need(self, authenticated_client):
        """Test updating nonexistent coverage requirement."""
        update_data = {
            'action': 'update_coverage',
            'need_id': '99999',
            'day_of_week': '1',
            'start_time': '10:00',
            'end_time': '16:00',
            'role_required': 'student',
            'required_count': '1'
        }
        response = authenticated_client.post('/staffing/', data=update_data, follow_redirects=True)
        assert response.status_code == 200

    def test_update_coverage_nonexistent_need_json(self, authenticated_client):
        """Test updating nonexistent coverage requirement (JSON mode)."""
        update_data = {
            'action': 'update_coverage',
            'need_id': '99999',
            'day_of_week': '1',
            'start_time': '10:00',
            'end_time': '16:00',
            'role_required': 'student',
            'required_count': '1',
            'fetch': '1'
        }
        response = authenticated_client.post('/staffing/', data=update_data)
        assert response.status_code == 404
        
        data = response.get_json()
        assert data['ok'] is False

    def test_update_coverage_locked_term(self, authenticated_client, locked_term, student_user):
        """Test updating coverage on locked term."""
        # Create need on locked term
        need = StaffingNeeds(
            term_id=locked_term.term_id,
            day_of_week=0,
            start_time=time(9, 0),
            end_time=time(17, 0),
            role_required='student',
            required_count=2
        )
        db.session.add(need)
        db.session.commit()

        update_data = {
            'action': 'update_coverage',
            'need_id': str(need.need_id),
            'day_of_week': '1',
            'start_time': '10:00',
            'end_time': '16:00',
            'role_required': 'student',
            'required_count': '1'
        }
        response = authenticated_client.post('/staffing/', data=update_data, follow_redirects=True)
        assert response.status_code == 200

    def test_update_coverage_locked_term_json(self, authenticated_client, locked_term, student_user):
        """Test updating coverage on locked term (JSON mode)."""
        # Create need on locked term
        need = StaffingNeeds(
            term_id=locked_term.term_id,
            day_of_week=0,
            start_time=time(9, 0),
            end_time=time(17, 0),
            role_required='student',
            required_count=2
        )
        db.session.add(need)
        db.session.commit()

        update_data = {
            'action': 'update_coverage',
            'need_id': str(need.need_id),
            'day_of_week': '1',
            'start_time': '10:00',
            'end_time': '16:00',
            'role_required': 'student',
            'required_count': '1',
            'fetch': '1'
        }
        response = authenticated_client.post('/staffing/', data=update_data)
        assert response.status_code == 400

    def test_update_coverage_invalid_time_range(self, authenticated_client, sample_staffing_need):
        """Test updating coverage with invalid time range."""
        update_data = {
            'action': 'update_coverage',
            'need_id': str(sample_staffing_need.need_id),
            'day_of_week': '1',
            'start_time': '16:00',
            'end_time': '10:00',  # End before start
            'role_required': 'student',
            'required_count': '1'
        }
        response = authenticated_client.post('/staffing/', data=update_data, follow_redirects=True)
        assert response.status_code == 200

    def test_update_coverage_exceeds_active_users(self, authenticated_client, sample_staffing_need):
        """Test updating coverage to exceed available users."""
        update_data = {
            'action': 'update_coverage',
            'need_id': str(sample_staffing_need.need_id),
            'day_of_week': '1',
            'start_time': '10:00',
            'end_time': '16:00',
            'role_required': 'student',
            'required_count': '100'  # Exceeds available
        }
        response = authenticated_client.post('/staffing/', data=update_data, follow_redirects=True)
        assert response.status_code == 200

    def test_update_coverage_overlap_existing(self, authenticated_client, sample_term, sample_staffing_need):
        """Test updating coverage to overlap with existing requirement."""
        # Create another staffing need
        other_need = StaffingNeeds(
            term_id=sample_term.term_id,
            day_of_week=1,  # Tuesday
            start_time=time(10, 0),
            end_time=time(16, 0),
            role_required='student',
            required_count=1
        )
        db.session.add(other_need)
        db.session.commit()

        # Try to update original need to overlap with other_need
        update_data = {
            'action': 'update_coverage',
            'need_id': str(sample_staffing_need.need_id),
            'day_of_week': '1',  # Same day as other_need
            'start_time': '12:00',  # Overlaps with other_need
            'end_time': '18:00',
            'role_required': 'student',
            'required_count': '1'
        }
        response = authenticated_client.post('/staffing/', data=update_data, follow_redirects=True)
        assert response.status_code == 200

    def test_update_coverage_database_exception(self, authenticated_client, sample_staffing_need, student_user):
        """Test updating coverage with database exception."""
        with patch('models.db.session.commit') as mock_commit:
            mock_commit.side_effect = Exception('Database error')
            update_data = {
                'action': 'update_coverage',
                'need_id': str(sample_staffing_need.need_id),
                'day_of_week': '1',
                'start_time': '10:00',
                'end_time': '16:00',
                'role_required': 'student',
                'required_count': '1'
            }
            response = authenticated_client.post('/staffing/', data=update_data, follow_redirects=True)
            assert response.status_code == 200

    def test_update_coverage_database_exception_json(self, authenticated_client, sample_staffing_need, student_user):
        """Test updating coverage with database exception (JSON mode)."""
        with patch('models.db.session.commit') as mock_commit:
            mock_commit.side_effect = Exception('Database error')
            update_data = {
                'action': 'update_coverage',
                'need_id': str(sample_staffing_need.need_id),
                'day_of_week': '1',
                'start_time': '10:00',
                'end_time': '16:00',
                'role_required': 'student',
                'required_count': '1',
                'fetch': '1'
            }
            response = authenticated_client.post('/staffing/', data=update_data)
            assert response.status_code == 500

    # ================= AUTHENTICATION TESTS =================

    def test_staffing_routes_require_authentication(self, client):
        """Test that all staffing routes require authentication."""
        # Test GET request
        response = client.get('/staffing/')
        assert response.status_code == 302  # Redirect to login

        # Test POST request
        response = client.post('/staffing/', data={'action': 'create_term'})
        assert response.status_code == 302  # Redirect to login

    # ================= EDGE CASES AND ERROR HANDLING =================

    def test_unknown_action(self, authenticated_client, sample_term):
        """Test POST request with unknown action."""
        unknown_data = {
            'action': 'unknown_action',
            'some_data': 'value'
        }
        response = authenticated_client.post('/staffing/', data=unknown_data, follow_redirects=True)
        assert response.status_code == 200

    def test_missing_action(self, authenticated_client):
        """Test POST request without action."""
        no_action_data = {
            'some_data': 'value'
        }
        response = authenticated_client.post('/staffing/', data=no_action_data, follow_redirects=True)
        assert response.status_code == 200

    def test_empty_post_data(self, authenticated_client):
        """Test POST request with empty data."""
        response = authenticated_client.post('/staffing/', data={}, follow_redirects=True)
        assert response.status_code == 200

    def test_malformed_post_data(self, authenticated_client):
        """Test POST request with malformed data."""
        # Test with invalid form data
        response = authenticated_client.post(
            '/staffing/',
            data="malformed=data&with=invalid&format",
            content_type='application/x-www-form-urlencoded',
            follow_redirects=True
        )
        assert response.status_code == 200

    def test_large_required_count(self, authenticated_client, sample_term):
        """Test handling of very large required count values."""
        coverage_data = {
            'action': 'add_coverage',
            'term_id': str(sample_term.term_id),
            'day_of_week': '0',
            'start_time': '09:00',
            'end_time': '17:00',
            'role_required': 'student',
            'required_count': '999999'
        }
        response = authenticated_client.post('/staffing/', data=coverage_data, follow_redirects=True)
        assert response.status_code == 200

    def test_boundary_time_values(self, authenticated_client, sample_term, student_user):
        """Test boundary time values (midnight, etc.)."""
        coverage_data = {
            'action': 'add_coverage',
            'term_id': str(sample_term.term_id),
            'day_of_week': '0',
            'start_time': '00:00',
            'end_time': '23:59',
            'role_required': 'student',
            'required_count': '1'
        }
        response = authenticated_client.post('/staffing/', data=coverage_data, follow_redirects=True)
        assert response.status_code == 200

    def test_utf8_term_names(self, authenticated_client):
        """Test term creation with UTF-8 characters."""
        term_data = {
            'action': 'create_term',
            'term_name': 'Spring 2025 – Special Characters ñáéíóú',
            'start_date': '2025-03-01',
            'end_date': '2025-06-01',
            'availability_deadline': '2025-02-28'
        }
        response = authenticated_client.post('/staffing/', data=term_data, follow_redirects=True)
        assert response.status_code == 200

    def test_multiple_terms_selection(self, authenticated_client, sample_term):
        """Test behavior with multiple terms."""
        # Create additional terms
        term2 = Term(
            name='Summer 2025',
            start_date=date(2025, 6, 1),
            end_date=date(2025, 8, 1),
            availability_deadline=date(2025, 5, 25),
            locked=False
        )
        term3 = Term(
            name='Fall 2025',
            start_date=date(2025, 8, 15),
            end_date=date(2025, 12, 15),
            availability_deadline=date(2025, 8, 10),
            locked=True
        )
        db.session.add_all([term2, term3])
        db.session.commit()

        # Test selecting specific terms
        response = authenticated_client.get(f'/staffing/?term_id={term2.term_id}')
        assert response.status_code == 200

        response = authenticated_client.get(f'/staffing/?term_id={term3.term_id}')
        assert response.status_code == 200

        # Test with all terms present
        response = authenticated_client.get('/staffing/')
        assert response.status_code == 200