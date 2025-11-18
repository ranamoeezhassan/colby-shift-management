import pytest
from models import db, User, Term, Policy, Shift, Availability
from blueprints.constraints.validation import (
    DurationValidator, 
    AutomaticRejectionSystem, 
    AutomaticSplitSystem, 
    ScheduleGenerator,
    ShiftValidationError
)
from blueprints.constraints.routes import validate_policy_data
from datetime import date, time, datetime, timedelta
from flask import url_for
import json


class TestPolicyModel:
    """Test Policy model basic operations and validations."""
    
    def test_policy_creation(self, app, db_session, sample_term, sample_user):
        """Test basic policy creation and retrieval."""
        with app.app_context():
            policy = Policy(
                term_id=sample_term.term_id,
                min_shift_length=60,
                max_shift_length=180,
                min_break_length=60,
                max_break_length=480,
                undesireable_start=600,
                undesireable_end=800,
                updated_by=sample_user.user_id
            )
            
            db.session.add(policy)
            db.session.commit()
            
            # Test retrieval
            retrieved_policy = Policy.query.filter_by(term_id=sample_term.term_id).first()
            assert retrieved_policy is not None
            assert retrieved_policy.min_shift_length == 60
            assert retrieved_policy.max_shift_length == 180
            assert retrieved_policy.min_break_length == 60
            assert retrieved_policy.max_break_length == 480
            assert retrieved_policy.undesireable_start == 600
            assert retrieved_policy.undesireable_end == 800
    
    def test_policy_duration_validation(self, app, db_session, sample_term, sample_user):
        """Test policy duration validation methods."""
        with app.app_context():
            policy = Policy(
                term_id=sample_term.term_id,
                min_shift_length=60,  # 1 hour
                max_shift_length=180,  # 3 hours
                min_break_length=60,
                max_break_length=480,
                undesireable_start=600,
                undesireable_end=800,
                updated_by=sample_user.user_id
            )
            
            db.session.add(policy)
            db.session.commit()
            
            # Test valid duration
            is_valid, error = policy.validate_shift_duration(120)  # 2 hours
            assert is_valid is True
            assert error is None
            
            # Test too short
            is_valid, error = policy.validate_shift_duration(30)  # 30 minutes
            assert is_valid is False
            assert "below minimum" in error
            
            # Test too long
            is_valid, error = policy.validate_shift_duration(240)  # 4 hours
            assert is_valid is False
            assert "exceeds maximum" in error
    
    def test_policy_time_validation(self, app, db_session, sample_term, sample_user):
        """Test policy shift time validation methods."""
        with app.app_context():
            policy = Policy(
                term_id=sample_term.term_id,
                min_shift_length=60,
                max_shift_length=180,
                min_break_length=60,
                max_break_length=480,
                undesireable_start=600,
                undesireable_end=800,
                updated_by=sample_user.user_id
            )
            
            db.session.add(policy)
            db.session.commit()
            
            # Test valid shift times
            start_time = time(9, 0)  # 9:00 AM
            end_time = time(11, 0)   # 11:00 AM (2 hours)
            is_valid, error = policy.validate_shift_times(start_time, end_time)
            assert is_valid is True
            assert error is None
            
            # Test shift too short
            start_time = time(9, 0)  # 9:00 AM
            end_time = time(9, 30)   # 9:30 AM (30 minutes)
            is_valid, error = policy.validate_shift_times(start_time, end_time)
            assert is_valid is False
            assert "below minimum" in error
            
            # Test shift too long
            start_time = time(9, 0)  # 9:00 AM
            end_time = time(13, 0)   # 1:00 PM (4 hours)
            is_valid, error = policy.validate_shift_times(start_time, end_time)
            assert is_valid is False
            assert "exceeds maximum" in error
    
    def test_policy_class_methods(self, app, db_session, sample_term, sample_user):
        """Test Policy class methods for finding policies."""
        with app.app_context():
            # Test no policy exists
            policy = Policy.get_policy_for_term(sample_term.term_id)
            assert policy is None
            
            # Create a policy
            policy = Policy(
                term_id=sample_term.term_id,
                min_shift_length=60,
                max_shift_length=180,
                min_break_length=60,
                max_break_length=480,
                undesireable_start=600,
                undesireable_end=800,
                updated_by=sample_user.user_id
            )
            
            db.session.add(policy)
            db.session.commit()
            
            # Test policy retrieval
            retrieved_policy = Policy.get_policy_for_term(sample_term.term_id)
            assert retrieved_policy is not None
            assert retrieved_policy.min_shift_length == 60
            
            # Test enforcement method
            start_time = time(10, 0)
            end_time = time(12, 0)
            is_valid, error, policy_returned = Policy.enforce_duration_constraints(
                sample_term.term_id, start_time, end_time
            )
            assert is_valid is True
            assert error is None
            assert policy_returned is not None
    
    def test_policy_with_defaults(self, app, db_session, sample_term):
        """Test getting policy with defaults when none exists."""
        with app.app_context():
            # Should return policy with default values
            policy = Policy.get_policy_with_defaults(sample_term.term_id)
            assert policy is not None
            assert policy.min_shift_length == 60
            assert policy.max_shift_length == 180
            assert policy.min_break_length == 60
            assert policy.max_break_length == 480
            assert policy.undesireable_start == 600
            assert policy.undesireable_end == 800
    
    def test_policy_default_values(self, app):
        """Test getting default policy values."""
        with app.app_context():
            defaults = Policy.get_default_values()
            assert defaults['min_shift_length'] == 60
            assert defaults['max_shift_length'] == 180
            assert defaults['min_break_length'] == 60
            assert defaults['max_break_length'] == 480
            assert defaults['undesireable_start'] == 600
            assert defaults['undesireable_end'] == 800


class TestTransitionTimeValidation:
    """Test transition time validation functionality."""
    
    def test_transition_time_validation(self, app, db_session, sample_term, sample_user):
        """Test transition time validation between consecutive shifts."""
        with app.app_context():
            policy = Policy(
                term_id=sample_term.term_id,
                min_shift_length=60,
                max_shift_length=180,
                min_break_length=60,
                max_break_length=480,
                undesireable_start=600,
                undesireable_end=800,
                min_transition_time=10,  # 10 minutes minimum
                transition_warning_enabled=True,
                updated_by=sample_user.user_id
            )
            
            db.session.add(policy)
            db.session.commit()
            
            # Test valid transition time
            first_end = time(10, 0)      # 10:00 AM
            second_start = time(10, 15)  # 10:15 AM (15 minutes later)
            
            is_valid, transition_minutes, error = policy.validate_transition_time(
                first_end, second_start
            )
            assert is_valid is True
            assert transition_minutes == 15
            assert error is None
            
            # Test insufficient transition time
            first_end = time(10, 0)     # 10:00 AM
            second_start = time(10, 5)  # 10:05 AM (5 minutes later)
            
            is_valid, transition_minutes, error = policy.validate_transition_time(
                first_end, second_start
            )
            assert is_valid is False
            assert transition_minutes == 5
            assert "Insufficient transition time" in error
    
    def test_overnight_transition_validation(self, app, db_session, sample_term, sample_user):
        """Test transition time validation for overnight shifts."""
        with app.app_context():
            policy = Policy(
                term_id=sample_term.term_id,
                min_shift_length=60,
                max_shift_length=180,
                min_break_length=60,
                max_break_length=480,
                undesireable_start=600,
                undesireable_end=800,
                min_transition_time=10,
                updated_by=sample_user.user_id
            )
            
            db.session.add(policy)
            db.session.commit()
            
            # Test overnight transition
            first_end = time(23, 0)    # 11:00 PM
            second_start = time(0, 30) # 12:30 AM next day (1.5 hours later)
            
            is_valid, transition_minutes, error = policy.validate_transition_time(
                first_end, second_start, date.today()
            )
            assert is_valid is True
            assert transition_minutes == 90  # 1.5 hours
            assert error is None


class TestDurationValidator:
    """Test the DurationValidator class."""
    
    def test_validate_shift_duration(self, app, db_session, sample_term, sample_user):
        """Test shift duration validation."""
        with app.app_context():
            # Create a policy first
            policy = Policy(
                term_id=sample_term.term_id,
                min_shift_length=60,
                max_shift_length=180,
                min_break_length=60,
                max_break_length=480,
                undesireable_start=600,
                undesireable_end=800,
                updated_by=sample_user.user_id
            )
            
            db.session.add(policy)
            db.session.commit()
            
            # Test valid duration
            start_time = time(9, 0)
            end_time = time(11, 0)  # 2 hours
            is_valid, error = DurationValidator.validate_shift_duration(
                sample_term.term_id, start_time, end_time
            )
            assert is_valid is True
            assert error is None
            
            # Test invalid duration
            start_time = time(9, 0)
            end_time = time(9, 30)  # 30 minutes
            is_valid, error = DurationValidator.validate_shift_duration(
                sample_term.term_id, start_time, end_time
            )
            assert is_valid is False
            assert error is not None
    
    def test_get_duration_minutes(self, app):
        """Test duration calculation in minutes."""
        with app.app_context():
            # Test normal shift
            start_time = time(9, 0)
            end_time = time(11, 0)
            duration = DurationValidator.get_duration_minutes(start_time, end_time)
            assert duration == 120  # 2 hours
            
            # Test overnight shift
            start_time = time(23, 0)
            end_time = time(1, 0)
            duration = DurationValidator.get_duration_minutes(start_time, end_time)
            assert duration == 120  # 2 hours overnight
    
    def test_enforce_minimum_maximum_duration(self, app, db_session, sample_term, sample_user):
        """Test minimum and maximum duration enforcement."""
        with app.app_context():
            # Create a policy first
            policy = Policy(
                term_id=sample_term.term_id,
                min_shift_length=60,
                max_shift_length=180,
                min_break_length=60,
                max_break_length=480,
                undesireable_start=600,
                undesireable_end=800,
                updated_by=sample_user.user_id
            )
            
            db.session.add(policy)
            db.session.commit()
            
            # Test minimum enforcement
            assert DurationValidator.enforce_minimum_duration(sample_term.term_id, 70) is True
            assert DurationValidator.enforce_minimum_duration(sample_term.term_id, 50) is False
            
            # Test maximum enforcement
            assert DurationValidator.enforce_maximum_duration(sample_term.term_id, 170) is True
            assert DurationValidator.enforce_maximum_duration(sample_term.term_id, 200) is False
    
    def test_get_policy_constraints(self, app, db_session, sample_term, sample_user):
        """Test getting policy constraints."""
        with app.app_context():
            # Test when no policy exists
            constraints = DurationValidator.get_policy_constraints(sample_term.term_id)
            assert constraints is None
            
            # Create a policy
            policy = Policy(
                term_id=sample_term.term_id,
                min_shift_length=60,
                max_shift_length=180,
                min_break_length=60,
                max_break_length=480,
                undesireable_start=600,
                undesireable_end=800,
                updated_by=sample_user.user_id
            )
            
            db.session.add(policy)
            db.session.commit()
            
            # Test when policy exists
            constraints = DurationValidator.get_policy_constraints(sample_term.term_id)
            assert constraints is not None
            assert constraints['min_duration'] == 60
            assert constraints['max_duration'] == 180
            assert constraints['min_break'] == 60
            assert constraints['max_break'] == 480
    
    def test_validate_shift_before_save(self, app, db_session, sample_term, sample_user):
        """Test validating shift data before saving."""
        with app.app_context():
            # Create a policy first
            policy = Policy(
                term_id=sample_term.term_id,
                min_shift_length=60,
                max_shift_length=180,
                min_break_length=60,
                max_break_length=480,
                undesireable_start=600,
                undesireable_end=800,
                updated_by=sample_user.user_id
            )
            
            db.session.add(policy)
            db.session.commit()
            
            # Test valid shift data
            shift_data = {
                'term_id': sample_term.term_id,
                'start_time': time(9, 0),
                'end_time': time(11, 0)
            }
            is_valid, error = DurationValidator.validate_shift_before_save(shift_data)
            assert is_valid is True
            assert error is None
            
            # Test invalid shift data
            shift_data = {
                'term_id': sample_term.term_id,
                'start_time': time(9, 0),
                'end_time': time(9, 30)
            }
            is_valid, error = DurationValidator.validate_shift_before_save(shift_data)
            assert is_valid is False
            assert error is not None
    
    def test_generate_error_message(self, app, db_session, sample_term, sample_user):
        """Test generating user-friendly error messages."""
        with app.app_context():
            # Create a policy first
            policy = Policy(
                term_id=sample_term.term_id,
                min_shift_length=60,
                max_shift_length=180,
                min_break_length=60,
                max_break_length=480,
                undesireable_start=600,
                undesireable_end=800,
                updated_by=sample_user.user_id
            )
            
            db.session.add(policy)
            db.session.commit()
            
            # Test too short error
            error_msg = DurationValidator.generate_error_message(sample_term.term_id, 30)
            assert "too short" in error_msg.lower()
            assert "30 minutes" in error_msg
            
            # Test too long error
            error_msg = DurationValidator.generate_error_message(sample_term.term_id, 240)
            assert "too long" in error_msg.lower()
            assert "240 minutes" in error_msg
            
            # Test valid duration
            error_msg = DurationValidator.generate_error_message(sample_term.term_id, 120)
            assert "valid" in error_msg.lower()


class TestAutomaticRejectionSystem:
    """Test automatic rejection system."""
    
    def test_auto_reject_short_shifts(self, app, db_session, sample_term, sample_user):
        """Test automatic rejection of shifts that are too short."""
        with app.app_context():
            # Create a policy first
            policy = Policy(
                term_id=sample_term.term_id,
                min_shift_length=60,  # 1 hour minimum
                max_shift_length=180,
                min_break_length=60,
                max_break_length=480,
                undesireable_start=600,
                undesireable_end=800,
                updated_by=sample_user.user_id
            )
            
            db.session.add(policy)
            db.session.commit()
            
            # Create test shifts with various durations
            proposed_shifts = [
                {
                    'start_time': time(9, 0),
                    'end_time': time(9, 30),   # 30 min - should be rejected
                    'date': date.today(),
                    'user_id': sample_user.user_id
                },
                {
                    'start_time': time(10, 0),
                    'end_time': time(11, 0),   # 60 min - should be accepted
                    'date': date.today(),
                    'user_id': sample_user.user_id
                },
                {
                    'start_time': time(14, 0),
                    'end_time': time(14, 45),  # 45 min - should be rejected
                    'date': date.today(),
                    'user_id': sample_user.user_id
                }
            ]
            
            # Test automatic rejection
            valid_shifts, rejected_shifts, coverage_warning = (
                AutomaticRejectionSystem.auto_reject_short_shifts(
                    sample_term.term_id, proposed_shifts
                )
            )
            
            # Should have 1 valid shift and 2 rejected shifts
            assert len(valid_shifts) == 1
            assert len(rejected_shifts) == 2
            assert coverage_warning is True  # Because shifts were rejected
            
            # Check that the valid shift is the 60-minute one
            assert valid_shifts[0]['start_time'] == time(10, 0)
            assert valid_shifts[0]['end_time'] == time(11, 0)
            
            # Check that rejected shifts have rejection reasons
            for rejected in rejected_shifts:
                assert 'rejection_reason' in rejected
                assert 'duration_minutes' in rejected
                assert 'below minimum' in rejected['rejection_reason']
    
    def test_get_rejection_stats(self, app, db_session, sample_term, sample_user):
        """Test getting rejection statistics."""
        with app.app_context():
            # Create a policy first
            policy = Policy(
                term_id=sample_term.term_id,
                min_shift_length=60,
                max_shift_length=180,
                min_break_length=60,
                max_break_length=480,
                undesireable_start=600,
                undesireable_end=800,
                updated_by=sample_user.user_id
            )
            
            db.session.add(policy)
            db.session.commit()
            
            # Test stats when no rejections exist
            stats = AutomaticRejectionSystem.get_rejection_stats(sample_term.term_id)
            assert stats['total_rejections'] == 0
            assert stats['duration_rejections'] == 0
            
            # Create some rejections by running the auto reject system
            proposed_shifts = [
                {
                    'start_time': time(9, 0),
                    'end_time': time(9, 30),   # 30 min - will be rejected
                    'date': date.today(),
                    'user_id': sample_user.user_id
                }
            ]
            
            AutomaticRejectionSystem.auto_reject_short_shifts(
                sample_term.term_id, proposed_shifts
            )
            
        # Get updated stats
        stats = AutomaticRejectionSystem.get_rejection_stats(sample_term.term_id)
        assert stats['total_rejections'] >= 1
        assert stats['duration_rejections'] >= 1
class TestAutomaticSplitSystem:
    """Test automatic split system."""
    
    def test_auto_split_long_shifts(self, app, db_session, sample_term, sample_user):
        """Test automatic splitting of shifts that are too long."""
        with app.app_context():
            # Create a policy first
            policy = Policy(
                term_id=sample_term.term_id,
                min_shift_length=60,   # 1 hour minimum
                max_shift_length=180,  # 3 hours maximum
                min_break_length=30,   # 30 minutes break
                max_break_length=480,
                undesireable_start=600,
                undesireable_end=800,
                updated_by=sample_user.user_id
            )
            
            db.session.add(policy)
            db.session.commit()
            
            # Create test shifts including one that's too long
            proposed_shifts = [
                {
                    'start_time': time(9, 0),
                    'end_time': time(11, 0),   # 2 hours - should be accepted
                    'date': date.today(),
                    'user_id': sample_user.user_id
                },
                {
                    'start_time': time(13, 0),
                    'end_time': time(18, 0),   # 5 hours - should be split
                    'date': date.today(),
                    'user_id': sample_user.user_id
                }
            ]
            
            # Test automatic splitting
            compliant_shifts, split_operations = (
                AutomaticSplitSystem.auto_split_long_shifts(
                    sample_term.term_id, proposed_shifts
                )
            )
            
            # Should have more shifts than originally proposed due to splitting
            assert len(compliant_shifts) > len(proposed_shifts)
            assert len(split_operations) == 1  # One shift was split
            
            # Check that all resulting shifts are compliant
            for shift in compliant_shifts:
                duration = DurationValidator.get_duration_minutes(
                    shift['start_time'], shift['end_time']
                )
                assert duration >= policy.min_shift_length
                assert duration <= policy.max_shift_length
    
    def test_split_and_log_shift(self, app, db_session, sample_term, sample_user):
        """Test splitting a specific long shift."""
        with app.app_context():
            # Create a policy first
            policy = Policy(
                term_id=sample_term.term_id,
                min_shift_length=60,
                max_shift_length=180,  # 3 hours maximum
                min_break_length=30,
                max_break_length=480,
                undesireable_start=600,
                undesireable_end=800,
                updated_by=sample_user.user_id
            )
            
            db.session.add(policy)
            db.session.commit()
            
            # Test splitting a 5-hour shift
            start_time = time(9, 0)
            end_time = time(14, 0)  # 5 hours
            shift_date = date.today()
            
            split_shifts = AutomaticSplitSystem.split_and_log_shift(
                sample_term.term_id, sample_user.user_id, start_time, end_time, shift_date
            )
            
            # Should have multiple split shifts
            assert len(split_shifts) >= 2
            
            # Check that each split shift is within policy limits
            for split_shift in split_shifts:
                duration = split_shift['duration_minutes']
                assert duration >= policy.min_shift_length
                assert duration <= policy.max_shift_length
            
            # Check that split shifts have proper sequence numbers
            for i, split_shift in enumerate(split_shifts):
                assert split_shift['split_sequence'] == i + 1
                assert split_shift['total_splits'] == len(split_shifts)
    
    def test_get_split_stats(self, app, db_session, sample_term, sample_user):
        """Test getting split statistics."""
        with app.app_context():
            # Create a policy first
            policy = Policy(
                term_id=sample_term.term_id,
                min_shift_length=60,
                max_shift_length=180,
                min_break_length=30,
                max_break_length=480,
                undesireable_start=600,
                undesireable_end=800,
                updated_by=sample_user.user_id
            )
            
            db.session.add(policy)
            db.session.commit()
            
            # Test stats when no splits exist
            stats = AutomaticSplitSystem.get_split_stats(sample_term.term_id)
            assert stats['total_splits'] == 0
            
            # Create a split by running the system
            proposed_shifts = [
                {
                    'start_time': time(9, 0),
                    'end_time': time(14, 0),   # 5 hours - will be split
                    'date': date.today(),
                    'user_id': sample_user.user_id
                }
            ]
            
            AutomaticSplitSystem.auto_split_long_shifts(
                sample_term.term_id, proposed_shifts
            )
            
            # Get updated stats
            stats = AutomaticSplitSystem.get_split_stats(sample_term.term_id)
            assert stats['total_splits'] >= 1


class TestScheduleGenerator:
    """Test the schedule generation with automatic processing."""
    
    def test_validate_proposed_shift(self, app, db_session, sample_term, sample_user):
        """Test validating a proposed shift."""
        with app.app_context():
            # Create a policy first
            policy = Policy(
                term_id=sample_term.term_id,
                min_shift_length=60,
                max_shift_length=180,
                min_break_length=60,
                max_break_length=480,
                undesireable_start=600,
                undesireable_end=800,
                updated_by=sample_user.user_id
            )
            
            db.session.add(policy)
            db.session.commit()
            
            # Test valid shift
            is_valid, error = ScheduleGenerator.validate_proposed_shift(
                sample_term.term_id, sample_user.user_id, time(9, 0), time(11, 0)
            )
            assert is_valid is True
            assert error is None
            
            # Test invalid shift
            is_valid, error = ScheduleGenerator.validate_proposed_shift(
                sample_term.term_id, sample_user.user_id, time(9, 0), time(9, 30)
            )
            assert is_valid is False
            assert error is not None
    
    def test_generate_schedule_with_auto_processing(self, app, db_session, sample_term, sample_user):
        """Test complete schedule generation with automatic processing."""
        with app.app_context():
            # Create a policy first
            policy = Policy(
                term_id=sample_term.term_id,
                min_shift_length=60,
                max_shift_length=180,
                min_break_length=30,
                max_break_length=480,
                undesireable_start=600,
                undesireable_end=800,
                updated_by=sample_user.user_id
            )
            
            db.session.add(policy)
            db.session.commit()
            
            # Create comprehensive test shifts
            proposed_shifts = [
                {
                    'start_time': time(9, 0),
                    'end_time': time(9, 30),    # Too short - will be rejected
                    'date': date.today(),
                    'user_id': sample_user.user_id
                },
                {
                    'start_time': time(10, 0),
                    'end_time': time(11, 0),    # Valid - will be accepted
                    'date': date.today(),
                    'user_id': sample_user.user_id
                },
                {
                    'start_time': time(13, 0),
                    'end_time': time(18, 0),    # Too long - will be split
                    'date': date.today(),
                    'user_id': sample_user.user_id
                }
            ]
            
            # Test the complete processing
            result = ScheduleGenerator.generate_schedule_with_auto_processing(
                sample_term.term_id, proposed_shifts
            )
            
            # Check that result contains all expected keys
            assert 'session_id' in result
            assert 'original_proposed' in result
            assert 'after_splits' in result
            assert 'final_valid_shifts' in result
            assert 'rejected_shifts' in result
            assert 'split_operations' in result
            assert 'coverage_warning' in result
            assert 'rejection_stats' in result
            assert 'split_stats' in result
            assert 'processing_summary' in result
            
            # Check processing summary
            summary = result['processing_summary']
            assert summary['original_count'] == 3
            assert summary['total_rejected'] >= 1  # Short shift should be rejected
            assert len(result['final_valid_shifts']) >= 1  # Should have some valid shifts
    
    def test_generate_valid_shift_options(self, app, db_session, sample_term, sample_user):
        """Test generating valid shift options from a start time."""
        with app.app_context():
            # Create a policy first
            policy = Policy(
                term_id=sample_term.term_id,
                min_shift_length=60,
                max_shift_length=180,
                min_break_length=60,
                max_break_length=480,
                undesireable_start=600,
                undesireable_end=800,
                updated_by=sample_user.user_id
            )
            
            db.session.add(policy)
            db.session.commit()
            
            # Test generating valid options
            start_time = time(9, 0)
            valid_options = ScheduleGenerator.generate_valid_shift_options(
                sample_term.term_id, start_time
            )
            
            assert len(valid_options) > 0
            
            # All options should create valid durations when paired with start time
            for end_time in valid_options:
                duration = DurationValidator.get_duration_minutes(start_time, end_time)
                assert duration >= policy.min_shift_length
                assert duration <= policy.max_shift_length


class TestShiftModel:
    """Test Shift model validation methods."""
    
    def test_shift_duration_calculation(self, app, db_session, sample_term, sample_user):
        """Test shift duration calculation."""
        with app.app_context():
            shift = Shift(
                term_id=sample_term.term_id,
                user_id=sample_user.user_id,
                date=date.today(),
                start_time=time(9, 0),
                end_time=time(11, 0)  # 2 hours
            )
            
            duration = shift.get_duration_minutes()
            assert duration == 120  # 2 hours in minutes
    
    def test_shift_validation_constraints(self, app, db_session, sample_term, sample_user):
        """Test shift duration constraint validation."""
        with app.app_context():
            # Create a policy first
            policy = Policy(
                term_id=sample_term.term_id,
                min_shift_length=60,
                max_shift_length=180,
                min_break_length=60,
                max_break_length=480,
                undesireable_start=600,
                undesireable_end=800,
                updated_by=sample_user.user_id
            )
            
            db.session.add(policy)
            db.session.commit()
            
            # Test valid shift
            shift = Shift(
                term_id=sample_term.term_id,
                user_id=sample_user.user_id,
                date=date.today(),
                start_time=time(9, 0),
                end_time=time(11, 0)  # 2 hours
            )
            
            is_valid, error = shift.validate_duration_constraints()
            assert is_valid is True
            assert error is None
            
            # Test invalid shift (too short)
            shift = Shift(
                term_id=sample_term.term_id,
                user_id=sample_user.user_id,
                date=date.today(),
                start_time=time(9, 0),
                end_time=time(9, 30)  # 30 minutes
            )
            
            is_valid, error = shift.validate_duration_constraints()
            assert is_valid is False
            assert "below minimum" in error
    
    def test_shift_validate_before_save(self, app, db_session, sample_term, sample_user):
        """Test the class method for validation before saving."""
        with app.app_context():
            # Create a policy first
            policy = Policy(
                term_id=sample_term.term_id,
                min_shift_length=60,
                max_shift_length=180,
                min_break_length=60,
                max_break_length=480,
                undesireable_start=600,
                undesireable_end=800,
                updated_by=sample_user.user_id
            )
            
            db.session.add(policy)
            db.session.commit()
            
            # Test valid shift times
            is_valid, error, policy_returned = Shift.validate_before_save(
                sample_term.term_id, time(9, 0), time(11, 0)
            )
            assert is_valid is True
            assert error is None
            assert policy_returned is not None


class TestPolicyDataValidation:
    """Test the policy data validation function."""
    
    def test_valid_policy_data(self, app):
        """Test validation of valid policy data."""
        with app.app_context():
            valid_data = {
                'term_id': 1,
                'min_shift_length': 60,
                'max_shift_length': 180,
                'min_break_length': 60,
                'max_break_length': 480,
                'undesirable_start': 600,
                'undesirable_end': 800
            }
            
            result = validate_policy_data(valid_data)
            assert result['valid'] is True
    
    def test_missing_required_fields(self, app):
        """Test validation with missing required fields."""
        with app.app_context():
            invalid_data = {
                'term_id': 1,
                'min_shift_length': 60,
                # Missing other required fields
            }
            
            result = validate_policy_data(invalid_data)
            assert result['valid'] is False
            assert 'required' in result['error']
    
    def test_invalid_shift_lengths(self, app):
        """Test validation with invalid shift lengths."""
        with app.app_context():
            # Test minimum too low
            invalid_data = {
                'term_id': 1,
                'min_shift_length': 20,  # Too low
                'max_shift_length': 180,
                'min_break_length': 60,
                'undesirable_start': 600,
                'undesirable_end': 800
            }
            
            result = validate_policy_data(invalid_data)
            assert result['valid'] is False
            assert 'less than 30 minutes' in result['error']
            
            # Test maximum too high
            invalid_data = {
                'term_id': 1,
                'min_shift_length': 60,
                'max_shift_length': 500,  # Too high
                'min_break_length': 60,
                'undesirable_start': 600,
                'undesirable_end': 800
            }
            
            result = validate_policy_data(invalid_data)
            assert result['valid'] is False
            assert 'exceed 8 hours' in result['error']
    
    def test_invalid_break_lengths(self, app):
        """Test validation with invalid break lengths."""
        with app.app_context():
            invalid_data = {
                'term_id': 1,
                'min_shift_length': 60,
                'max_shift_length': 180,
                'min_break_length': -10,  # Negative
                'max_break_length': 60,
                'undesirable_start': 600,
                'undesirable_end': 800
            }
            
            result = validate_policy_data(invalid_data)
            assert result['valid'] is False
            assert 'cannot be negative' in result['error']
    
    def test_invalid_undesirable_times(self, app):
        """Test validation with invalid undesirable times."""
        with app.app_context():
            invalid_data = {
                'term_id': 1,
                'min_shift_length': 60,
                'max_shift_length': 180,
                'min_break_length': 60,
                'undesirable_start': 2500,  # Invalid time
                'undesirable_end': 800
            }
            
            result = validate_policy_data(invalid_data)
            assert result['valid'] is False
            assert 'between 0000 and 2359' in result['error']


class TestCompatibilityWrappers:
    """Test the compatibility wrapper classes."""
    
    def test_shift_violation_wrapper(self, app, db_session, sample_term, sample_user):
        """Test ShiftViolation compatibility wrapper."""
        with app.app_context():
            from models import ShiftViolation
            
            # Create a policy first
            policy = Policy(
                term_id=sample_term.term_id,
                min_shift_length=60,
                max_shift_length=180,
                min_break_length=60,
                max_break_length=480,
                undesireable_start=600,
                undesireable_end=800,
                updated_by=sample_user.user_id
            )
            
            db.session.add(policy)
            db.session.commit()
            
            # Create a shift that violates constraints
            shift = Shift(
                term_id=sample_term.term_id,
                user_id=sample_user.user_id,
                date=date.today(),
                start_time=time(9, 0),
                end_time=time(9, 30)  # Too short
            )
            
            db.session.add(shift)
            db.session.commit()
            
            # Test wrapper method
            violations = ShiftViolation.detect_violations_for_shift(shift)
            assert len(violations) > 0
            
            # Test summary method
            summary = ShiftViolation.get_violation_summary(sample_term.term_id)
            assert 'total_violations' in summary
    
    def test_shift_gap_wrapper(self, app, db_session, sample_term, sample_user):
        """Test ShiftGap compatibility wrapper."""
        with app.app_context():
            from models import ShiftGap
            
            # Create a policy first
            policy = Policy(
                term_id=sample_term.term_id,
                min_shift_length=60,
                max_shift_length=180,
                min_break_length=60,
                max_break_length=480,
                undesireable_start=600,
                undesireable_end=800,
                min_gap_threshold=15,
                max_gap_threshold=30,
                updated_by=sample_user.user_id
            )
            
            db.session.add(policy)
            db.session.commit()
            
            # Test wrapper methods
            gaps = ShiftGap.detect_gaps_for_user_date(
                sample_user.user_id, date.today(), sample_term.term_id
            )
            assert isinstance(gaps, list)
            
            summary = ShiftGap.get_gap_summary(sample_term.term_id, sample_user.user_id)
            assert 'total_gaps' in summary


class TestPolicyJSONFields:
    """Test Policy JSON field functionality for consolidated data storage."""
    
    def test_undesirable_windows_management(self, app, db_session, sample_term, sample_user):
        """Test undesirable windows JSON field management."""
        with app.app_context():
            policy = Policy(
                term_id=sample_term.term_id,
                min_shift_length=60,
                max_shift_length=180,
                min_break_length=60,
                max_break_length=480,
                undesireable_start=600,
                undesireable_end=800,
                updated_by=sample_user.user_id
            )
            
            db.session.add(policy)
            db.session.commit()
            
            # Test adding undesirable window
            policy.add_undesirable_window(
                name="Early Morning",
                start_time=time(6, 0),
                end_time=time(8, 0),
                day_of_week=1,  # Monday
                weight=1.5
            )
            
            # Test retrieving windows
            windows = policy.get_undesirable_windows()
            assert len(windows) == 1
            assert windows[0]['name'] == "Early Morning"
            assert windows[0]['start_time'] == "06:00"
            assert windows[0]['end_time'] == "08:00"
            assert windows[0]['day_of_week'] == 1
            assert windows[0]['weight'] == 1.5
            
            # Test removing window
            window_id = windows[0]['window_id']
            policy.remove_undesirable_window(window_id)
            
            windows = policy.get_undesirable_windows()
            assert len(windows) == 0
    
    def test_shift_violations_tracking(self, app, db_session, sample_term, sample_user):
        """Test shift violations JSON field tracking."""
        with app.app_context():
            policy = Policy(
                term_id=sample_term.term_id,
                min_shift_length=60,
                max_shift_length=180,
                min_break_length=60,
                max_break_length=480,
                undesireable_start=600,
                undesireable_end=800,
                updated_by=sample_user.user_id
            )
            
            db.session.add(policy)
            db.session.commit()
            
            # Create a shift that violates constraints
            shift = Shift(
                term_id=sample_term.term_id,
                user_id=sample_user.user_id,
                date=date.today(),
                start_time=time(9, 0),
                end_time=time(9, 30)  # Too short - 30 minutes
            )
            
            db.session.add(shift)
            db.session.commit()
            
            # Test detecting violations
            violations = policy.detect_violations_for_shift(shift)
            assert len(violations) == 1
            assert violations[0]['violation_type'] == 'too_short'
            assert violations[0]['current_duration'] == 30
            assert violations[0]['expected_min'] == 60
            
            # Test violation summary
            summary = policy.get_violation_summary()
            assert summary['total_violations'] == 1
            assert summary['by_severity']['error'] == 1
            assert summary['by_type']['too_short'] == 1
    
    def test_audit_logging(self, app, db_session, sample_term, sample_user):
        """Test policy change audit logging."""
        with app.app_context():
            policy = Policy(
                term_id=sample_term.term_id,
                min_shift_length=60,
                max_shift_length=180,
                min_break_length=60,
                max_break_length=480,
                undesireable_start=600,
                undesireable_end=800,
                updated_by=sample_user.user_id
            )
            
            db.session.add(policy)
            db.session.commit()
            
            # Test logging a policy change
            policy.log_policy_change(
                user_id=sample_user.user_id,
                change_type='update',
                field_name='min_shift_length',
                old_value=60,
                new_value=90,
                reason='Increased minimum to reduce short shifts'
            )
            
            # Check that audit log was created
            assert policy.audit_log is not None
            assert len(policy.audit_log) == 1
            
            audit_entry = policy.audit_log[0]
            assert audit_entry['change_type'] == 'update'
            assert audit_entry['field_name'] == 'min_shift_length'
            assert audit_entry['old_value'] == '60'
            assert audit_entry['new_value'] == '90'
            assert audit_entry['change_reason'] == 'Increased minimum to reduce short shifts'
    
    def test_validation_report_generation(self, app, db_session, sample_term, sample_user):
        """Test validation report generation and storage."""
        with app.app_context():
            policy = Policy(
                term_id=sample_term.term_id,
                min_shift_length=60,
                max_shift_length=180,
                min_break_length=60,
                max_break_length=480,
                undesireable_start=600,
                undesireable_end=800,
                updated_by=sample_user.user_id
            )
            
            db.session.add(policy)
            db.session.commit()
            
            # Generate a validation report
            report = policy.generate_validation_report(sample_user.user_id)
            
            assert report is not None
            assert 'report_id' in report
            assert 'generated_by' in report
            assert 'total_violations_found' in report
            assert 'report_summary' in report
            assert report['report_status'] == 'completed'
            
            # Check that report was stored in JSON field
            assert policy.validation_reports is not None
            assert len(policy.validation_reports) == 1


class TestErrorHandling:
    """Test error handling in constraint validation."""
    
    def test_missing_policy_error(self, app, db_session, sample_term):
        """Test handling of missing policy errors."""
        with app.app_context():
            # Try to validate without creating a policy first
            with pytest.raises(ShiftValidationError):
                DurationValidator.validate_shift_duration(
                    sample_term.term_id, time(9, 0), time(11, 0)
                )
    
    def test_invalid_term_error(self, app, db_session):
        """Test handling of invalid term errors."""
        with app.app_context():
            # Try to validate with non-existent term
            constraints = DurationValidator.get_policy_constraints(99999)
            assert constraints is None
    
    def test_validation_error_propagation(self, app, db_session, sample_term, sample_user):
        """Test that validation errors are properly propagated."""
        with app.app_context():
            # Create a policy
            policy = Policy(
                term_id=sample_term.term_id,
                min_shift_length=60,
                max_shift_length=180,
                min_break_length=60,
                max_break_length=480,
                undesireable_start=600,
                undesireable_end=800,
                updated_by=sample_user.user_id
            )
            
            db.session.add(policy)
            db.session.commit()
            
            # Test that validation errors contain helpful information
            is_valid, error = DurationValidator.validate_shift_duration(
                sample_term.term_id, time(9, 0), time(9, 15)  # 15 minutes - too short
            )
            
            assert is_valid is False
            assert error is not None
            assert "15" in error  # Should mention actual duration
            assert "60" in error  # Should mention required minimum


if __name__ == "__main__":
    pytest.main([__file__])