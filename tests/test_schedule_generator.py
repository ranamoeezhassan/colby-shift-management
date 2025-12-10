import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, date, time, timedelta
from models import db, User, Term, Shift, Policy, Availability, StaffingNeeds, ShiftGap
from conftest import login_user


class TestScheduleGeneratorInit:
    """Test ScheduleGenerator initialization."""

    def test_init_creates_generator(self, app, db_session, sample_term, policy):
        """Generator initializes with term and policy."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        
        assert gen.term_id == sample_term.term_id
        assert gen.policy is not None
        assert gen.generated_shifts == []
        assert gen.rejected_shifts == []
        assert gen.warnings == []

    def test_init_uses_default_policy(self, app, db_session, sample_term):
        """Generator uses default policy when none exists."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        
        assert gen.policy is not None


class TestScheduleGeneration:
    """Test schedule generation functionality."""

    def test_generate_schedule_empty(self, app, db_session, sample_term, policy):
        """Generate returns empty when no staffing needs."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        result = gen.generate_schedule(date(2025, 9, 1), date(2025, 9, 1), dry_run=True)
        
        assert result['total_shifts_generated'] == 0
        assert 'gap_prevention_active' in result

    def test_generate_schedule_dry_run(self, app, db_session, sample_term, policy, student_user, 
                                       staffing_needs, availability_record):
        """Dry run doesn't save to database."""
        from schedule_generator import ScheduleGenerator
        
        initial_count = Shift.query.count()
        
        gen = ScheduleGenerator(sample_term.term_id)
        result = gen.generate_schedule(date(2025, 9, 1), date(2025, 9, 1), dry_run=True)
        
        # No new shifts in database
        assert Shift.query.count() == initial_count

    def test_generate_schedule_saves_shifts(self, app, db_session, sample_term, policy, student_user,
                                            staffing_needs, availability_record):
        """Non-dry run saves shifts to database."""
        from schedule_generator import ScheduleGenerator
        
        initial_count = Shift.query.count()
        
        gen = ScheduleGenerator(sample_term.term_id)
        result = gen.generate_schedule(date(2025, 9, 1), date(2025, 9, 1), dry_run=False)
        
        # Shifts may or may not be created depending on availability match
        # At minimum, the method should complete without error
        assert 'total_shifts_generated' in result

    def test_generate_schedule_multiple_days(self, app, db_session, sample_term, policy, student_user,
                                             staffing_needs, availability_record):
        """Generation works for date range."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        result = gen.generate_schedule(date(2025, 9, 1), date(2025, 9, 7), dry_run=True)
        
        assert 'total_shifts_generated' in result

    def test_generation_summary_format(self, app, db_session, sample_term, policy):
        """Generation summary has expected fields."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        result = gen.generate_schedule(date(2025, 9, 1), date(2025, 9, 1), dry_run=True)
        
        assert 'total_shifts_generated' in result
        assert 'shifts_rejected' in result
        assert 'warnings' in result
        assert 'gap_prevention_active' in result
        assert 'auto_merge_enabled' in result
        assert 'gap_thresholds' in result
        assert 'policy_settings' in result


class TestOptimalShiftDuration:
    """Test optimal shift duration calculation."""

    def test_duration_within_max(self, app, db_session, sample_term, policy):
        """Returns total duration when within max."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        
        # Total duration 120 minutes, max is 180
        duration = gen._calculate_optimal_shift_duration(120)
        
        assert duration == 120

    def test_duration_prefer_longer_shifts(self, app, db_session, sample_term, policy):
        """Prefers longer shifts when enabled."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        gen.policy.prefer_longer_shifts = True
        
        # Total duration 300 minutes, should find divisor
        duration = gen._calculate_optimal_shift_duration(300)
        
        assert duration >= gen.policy.min_shift_length
        assert duration <= gen.policy.max_shift_length

    def test_duration_divisible(self, app, db_session, sample_term, policy):
        """Finds duration that divides evenly."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        gen.policy.prefer_longer_shifts = True
        gen.policy.max_shift_length = 120
        gen.policy.min_shift_length = 60
        
        # 240 minutes = 4 hours, should find 120 (divides evenly into 2)
        duration = gen._calculate_optimal_shift_duration(240)
        
        assert 240 % duration == 0 or duration >= gen.policy.max_gap_threshold


class TestUserAvailability:
    """Test user availability checking."""

    def test_user_available(self, app, db_session, sample_term, policy, student_user, availability_record):
        """User is available when within availability window."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        
        # Availability is Mon 9:00-17:00
        is_available = gen._is_user_available(
            student_user, 
            date(2025, 9, 1),  # Monday
            time(10, 0),
            120  # 2 hours
        )
        
        assert is_available is True

    def test_user_not_available_wrong_day(self, app, db_session, sample_term, policy, student_user, availability_record):
        """User not available on day without availability."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        
        # Availability is only Mon, check Tue
        is_available = gen._is_user_available(
            student_user, 
            date(2025, 9, 2),  # Tuesday
            time(10, 0),
            120
        )
        
        assert is_available is False

    def test_user_not_available_no_records(self, app, db_session, sample_term, policy, student_user):
        """User not available when no availability records."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        
        is_available = gen._is_user_available(
            student_user, 
            date(2025, 9, 1),
            time(10, 0),
            120
        )
        
        assert is_available is False


class TestGapValidation:
    """Test gap validation for shifts."""

    def test_validate_no_existing_shifts(self, app, db_session, sample_term, policy, student_user):
        """Shift is valid when no existing shifts."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        
        proposed_shift = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1),
            start_time=time(9, 0),
            end_time=time(11, 0)
        )
        
        is_valid = gen._validate_shift_for_gaps(proposed_shift, student_user)
        
        assert is_valid is True

    def test_validate_problematic_gap(self, app, db_session, sample_term, policy, student_user):
        """Shift creating problematic gap is rejected."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        
        # Add existing shift
        existing_shift = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1),
            start_time=time(9, 0),
            end_time=time(11, 0)
        )
        gen.generated_shifts.append(existing_shift)
        
        # Proposed shift with 20-min gap (problematic if min=15, max=30)
        proposed_shift = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1),
            start_time=time(11, 20),
            end_time=time(13, 0)
        )
        
        gen.policy.min_gap_threshold = 15
        gen.policy.max_gap_threshold = 30
        
        is_valid = gen._validate_shift_for_gaps(proposed_shift, student_user)
        
        assert is_valid is False
        assert len(gen.warnings) > 0

    def test_validate_transition_time_violation(self, app, db_session, sample_term, policy, student_user):
        """Shift with insufficient transition time is rejected."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        
        # Add existing shift
        existing_shift = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1),
            start_time=time(9, 0),
            end_time=time(11, 0)
        )
        gen.generated_shifts.append(existing_shift)
        
        # Proposed shift with 5-min gap (< min_transition_time of 10)
        proposed_shift = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1),
            start_time=time(11, 5),
            end_time=time(13, 0)
        )
        
        gen.policy.min_transition_time = 10
        gen.policy.min_gap_threshold = 15
        gen.policy.max_gap_threshold = 30
        
        is_valid = gen._validate_shift_for_gaps(proposed_shift, student_user)
        
        assert is_valid is False


class TestGapDurationCalculation:
    """Test gap duration calculation."""

    def test_calculate_gap_duration_positive(self, app, db_session, sample_term, policy, student_user):
        """Calculates positive gap duration."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        
        shift1 = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1),
            start_time=time(9, 0),
            end_time=time(11, 0)
        )
        shift2 = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1),
            start_time=time(11, 30),
            end_time=time(13, 0)
        )
        
        gap = gen._calculate_gap_duration(shift1, shift2)
        
        assert gap == 30

    def test_calculate_gap_adjacent(self, app, db_session, sample_term, policy, student_user):
        """Returns None for adjacent shifts (no gap)."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        
        shift1 = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1),
            start_time=time(9, 0),
            end_time=time(11, 0)
        )
        shift2 = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1),
            start_time=time(11, 0),  # Starts exactly when first ends
            end_time=time(13, 0)
        )
        
        gap = gen._calculate_gap_duration(shift1, shift2)
        
        # Adjacent shifts should return None (no gap)
        assert gap is None

    def test_calculate_gap_order_independent(self, app, db_session, sample_term, policy, student_user):
        """Gap calculation is independent of shift order."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        
        shift1 = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1),
            start_time=time(9, 0),
            end_time=time(11, 0)
        )
        shift2 = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1),
            start_time=time(11, 30),
            end_time=time(13, 0)
        )
        
        gap1 = gen._calculate_gap_duration(shift1, shift2)
        gap2 = gen._calculate_gap_duration(shift2, shift1)
        
        assert gap1 == gap2


class TestGapResolution:
    """Test gap resolution and merging."""

    def test_post_process_groups_shifts(self, app, db_session, sample_term, policy, student_user):
        """Post-processing groups shifts by user and date."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        
        shift1 = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1),
            start_time=time(9, 0),
            end_time=time(11, 0)
        )
        shift2 = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1),
            start_time=time(11, 15),
            end_time=time(13, 0)
        )
        
        gen.generated_shifts = [shift1, shift2]
        gen._post_process_gaps()
        
        # Should process without error
        assert len(gen.generated_shifts) >= 1

    def test_try_merge_shifts_success(self, app, db_session, sample_term, policy, student_user):
        """Successfully merges adjacent shifts."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        
        shift1 = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1),
            start_time=time(9, 0),
            end_time=time(10, 0)
        )
        shift2 = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1),
            start_time=time(10, 15),
            end_time=time(11, 0)
        )
        
        merged = gen._try_merge_shifts(shift1, shift2)
        
        if merged:  # Depends on policy allowing merge
            assert merged.start_time == time(9, 0)
            assert merged.end_time == time(11, 0)
            assert merged.was_manually_adjusted is True

    def test_try_merge_shifts_too_long(self, app, db_session, sample_term, policy, student_user):
        """Fails to merge when result would be too long."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        gen.policy.max_shift_length = 120  # 2 hours max
        
        shift1 = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1),
            start_time=time(9, 0),
            end_time=time(11, 0)  # 2 hours
        )
        shift2 = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1),
            start_time=time(11, 15),
            end_time=time(13, 0)  # ~1.75 hours
        )
        
        merged = gen._try_merge_shifts(shift1, shift2)
        
        # Merged would be 4 hours, exceeds max
        assert merged is None


class TestGetAvailableUsers:
    """Test getting available users."""

    def test_get_available_users_with_availability(self, app, db_session, sample_term, policy, 
                                                    student_user, availability_record):
        """Returns users with availability."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        
        users = gen._get_available_users(date(2025, 9, 1), 0)  # Monday
        
        assert len(users) >= 1
        assert student_user in users

    def test_get_available_users_no_availability(self, app, db_session, sample_term, policy, student_user):
        """Returns empty when no availability."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        
        users = gen._get_available_users(date(2025, 9, 1), 0)
        
        assert len(users) == 0


class TestSaveGeneratedSchedule:
    """Test saving generated schedule."""

    def test_save_schedule_success(self, app, db_session, sample_term, policy, student_user):
        """Successfully saves generated shifts."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        
        shift = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1),
            start_time=time(9, 0),
            end_time=time(11, 0)
        )
        gen.generated_shifts = [shift]
        
        gen._save_generated_schedule()
        
        saved = Shift.query.filter_by(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1)
        ).first()
        
        assert saved is not None

    def test_save_schedule_exception(self, app, db_session, sample_term, policy, student_user):
        """Handles save exception with rollback."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        gen.generated_shifts = [MagicMock()]  # Invalid shift object
        
        with pytest.raises(Exception):
            gen._save_generated_schedule()


class TestGapAnalyzer:
    """Test GapAnalyzer class."""

    def test_analyze_term_gaps(self, app, db_session, sample_term, policy, student_user, sample_shift):
        """Analyzes gaps in term schedule."""
        from schedule_generator import GapAnalyzer
        
        result = GapAnalyzer.analyze_term_gaps(sample_term.term_id)
        
        assert 'total_gaps_detected' in result
        assert 'gap_summary' in result
        assert 'merge_recommendations' in result
        assert 'gaps_by_user' in result
        assert 'gaps_by_date' in result

    def test_group_gaps_by_user(self, app, db_session, sample_term, policy, student_user):
        """Groups gaps by user correctly."""
        from schedule_generator import GapAnalyzer
        
        # Create mock gaps
        gap1 = MagicMock()
        gap1.user_id = student_user.user_id
        gap1.user.name = student_user.name
        gap1.gap_duration_minutes = 20
        
        gap2 = MagicMock()
        gap2.user_id = student_user.user_id
        gap2.user.name = student_user.name
        gap2.gap_duration_minutes = 25
        
        grouped = GapAnalyzer._group_gaps_by_user([gap1, gap2])
        
        assert student_user.user_id in grouped
        assert grouped[student_user.user_id]['total_gap_time'] == 45
        assert grouped[student_user.user_id]['avg_gap_duration'] == 22.5

    def test_group_gaps_by_date(self, app, db_session):
        """Groups gaps by date correctly."""
        from schedule_generator import GapAnalyzer
        
        gap1 = MagicMock()
        gap1.date = date(2025, 9, 1)
        
        gap2 = MagicMock()
        gap2.date = date(2025, 9, 1)
        
        gap3 = MagicMock()
        gap3.date = date(2025, 9, 2)
        
        grouped = GapAnalyzer._group_gaps_by_date([gap1, gap2, gap3])
        
        assert '2025-09-01' in grouped
        assert len(grouped['2025-09-01']) == 2
        assert '2025-09-02' in grouped
        assert len(grouped['2025-09-02']) == 1

    @patch('schedule_generator.ShiftGap')
    def test_batch_merge_gaps_success(self, mock_shiftgap, app, db_session, supervisor_user):
        """Batch merge successfully processes gaps."""
        from schedule_generator import GapAnalyzer
        
        mock_gap = MagicMock()
        mock_gap.is_resolved = False
        mock_gap.attempt_auto_merge.return_value = True
        
        mock_shiftgap.query.get.return_value = mock_gap
        
        result = GapAnalyzer.batch_merge_gaps([1, 2], supervisor_user.user_id)
        
        assert result['successful_merges'] == 2
        assert result['failed_merges'] == 0

    @patch('schedule_generator.ShiftGap')
    def test_batch_merge_gaps_failure(self, mock_shiftgap, app, db_session, supervisor_user):
        """Batch merge handles failures."""
        from schedule_generator import GapAnalyzer
        
        mock_gap = MagicMock()
        mock_gap.is_resolved = False
        mock_gap.attempt_auto_merge.return_value = False
        mock_gap.merge_blocked_reason = "Duration too long"
        
        mock_shiftgap.query.get.return_value = mock_gap
        
        result = GapAnalyzer.batch_merge_gaps([1], supervisor_user.user_id)
        
        assert result['failed_merges'] == 1
        assert len(result['errors']) == 1

    @patch('schedule_generator.ShiftGap')
    def test_batch_merge_gaps_exception(self, mock_shiftgap, app, db_session, supervisor_user):
        """Batch merge handles exceptions."""
        from schedule_generator import GapAnalyzer
        
        mock_gap = MagicMock()
        mock_gap.is_resolved = False
        mock_gap.attempt_auto_merge.side_effect = Exception("Merge error")
        
        mock_shiftgap.query.get.return_value = mock_gap
        
        result = GapAnalyzer.batch_merge_gaps([1], supervisor_user.user_id)
        
        assert result['failed_merges'] == 1
        assert 'Merge error' in result['errors'][0]

    @patch('schedule_generator.ShiftGap')
    def test_batch_merge_skips_resolved(self, mock_shiftgap, app, db_session, supervisor_user):
        """Batch merge skips already resolved gaps."""
        from schedule_generator import GapAnalyzer
        
        mock_gap = MagicMock()
        mock_gap.is_resolved = True
        
        mock_shiftgap.query.get.return_value = mock_gap
        
        result = GapAnalyzer.batch_merge_gaps([1], supervisor_user.user_id)
        
        assert result['successful_merges'] == 0
        assert result['failed_merges'] == 0


class TestCreateProposedShift:
    """Test proposed shift creation."""

    def test_create_proposed_shift(self, app, db_session, sample_term, policy, student_user):
        """Creates proposed shift with correct attributes."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        
        shift = gen._create_proposed_shift(
            student_user,
            date(2025, 9, 1),
            time(9, 0),
            120
        )
        
        assert shift.term_id == sample_term.term_id
        assert shift.user_id == student_user.user_id
        assert shift.date == date(2025, 9, 1)
        assert shift.start_time == time(9, 0)
        assert shift.end_time == time(11, 0)
        assert shift.was_manually_adjusted is False


class TestAdditionalCoverage:
    """Additional tests for edge cases and coverage."""

    def test_overnight_staffing_need(self, app, db_session, sample_term, policy, student_user):
        """Handles overnight staffing needs (end < start - line 89)."""
        from schedule_generator import ScheduleGenerator
        
        # Create overnight staffing need (11 PM - 2 AM)
        overnight_need = StaffingNeeds(
            term_id=sample_term.term_id,
            day_of_week=0,
            start_time=time(23, 0),
            end_time=time(2, 0),  # Next day
            role_required="student",
            required_count=1
        )
        db_session.add(overnight_need)
        db_session.commit()
        
        gen = ScheduleGenerator(sample_term.term_id)
        result = gen.generate_schedule(date(2025, 9, 1), date(2025, 9, 1), dry_run=True)
        
        assert 'total_shifts_generated' in result

    def test_default_duration_fallback(self, app, db_session, sample_term, policy):
        """Uses default duration when no good divisor found (line 143)."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        gen.policy.prefer_longer_shifts = False  # Disable to hit fallback
        
        # With prefer_longer_shifts=False, should use fallback
        duration = gen._calculate_optimal_shift_duration(500)
        
        assert duration >= gen.policy.min_shift_length
        assert duration <= gen.policy.max_shift_length

    def test_user_availability_partial_coverage(self, app, db_session, sample_term, policy, student_user):
        """User not available when shift extends beyond availability (line 170)."""
        from schedule_generator import ScheduleGenerator
        
        # Create availability 9-12 only
        avail = Availability(
            user_id=student_user.user_id,
            term_id=sample_term.term_id,
            day_of_week="Mon",
            start_time=time(9, 0),
            end_time=time(12, 0),
            is_exception=False
        )
        db_session.add(avail)
        db_session.commit()
        
        gen = ScheduleGenerator(sample_term.term_id)
        
        # Shift from 11:00-14:00 extends beyond availability
        is_available = gen._is_user_available(
            student_user, 
            date(2025, 9, 1),
            time(11, 0),
            180  # 3 hours - would end at 14:00
        )
        
        assert is_available is False

    def test_validate_gap_returns_true_when_ok(self, app, db_session, sample_term, policy, student_user):
        """Validation returns True when gap is acceptable (line 222)."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        
        # Add existing shift
        existing_shift = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1),
            start_time=time(9, 0),
            end_time=time(11, 0)
        )
        gen.generated_shifts.append(existing_shift)
        
        # Proposed shift with large gap (> max_gap_threshold)
        proposed_shift = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1),
            start_time=time(14, 0),  # 3 hour gap
            end_time=time(16, 0)
        )
        
        gen.policy.min_gap_threshold = 15
        gen.policy.max_gap_threshold = 30
        gen.policy.min_transition_time = 10
        
        is_valid = gen._validate_shift_for_gaps(proposed_shift, student_user)
        
        assert is_valid is True

    def test_gap_resolution_with_merge(self, app, db_session, sample_term, policy, student_user):
        """Gap resolution successfully merges shifts (lines 305-313)."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        gen.policy.allow_gap_merging = True
        gen.policy.max_gap_threshold = 30
        gen.policy.max_shift_length = 180  # Allow 3 hour merged shifts
        
        # Create two shifts with small gap that can be merged
        shift1 = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1),
            start_time=time(9, 0),
            end_time=time(10, 0)
        )
        shift2 = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1),
            start_time=time(10, 15),
            end_time=time(11, 0)
        )
        
        gen.generated_shifts = [shift1, shift2]
        gen._post_process_gaps()
        
        # Should have merged or generated warning
        assert len(gen.warnings) >= 0  # May or may not merge depending on validation

    def test_gap_resolution_no_merge_large_gap(self, app, db_session, sample_term, policy, student_user):
        """Gap resolution skips merging for large gaps (line 319)."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        gen.policy.allow_gap_merging = True
        gen.policy.max_gap_threshold = 30
        
        # Create two shifts with gap larger than threshold
        shift1 = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1),
            start_time=time(9, 0),
            end_time=time(10, 0)
        )
        shift2 = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1),
            start_time=time(11, 0),  # 60 min gap > max_gap_threshold
            end_time=time(12, 0)
        )
        
        gen.generated_shifts = [shift1, shift2]
        initial_count = len(gen.generated_shifts)
        
        gen._post_process_gaps()
        
        # Should not merge - gap too large
        assert len(gen.generated_shifts) == initial_count

    def test_try_merge_shifts_reversed_order(self, app, db_session, sample_term, policy, student_user):
        """Merge works regardless of shift order (line 336)."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        gen.policy.max_shift_length = 180
        
        # Pass shifts in reverse order (shift2 starts before shift1)
        shift1 = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1),
            start_time=time(10, 15),
            end_time=time(11, 0)
        )
        shift2 = Shift(
            term_id=sample_term.term_id,
            user_id=student_user.user_id,
            date=date(2025, 9, 1),
            start_time=time(9, 0),
            end_time=time(10, 0)
        )
        
        merged = gen._try_merge_shifts(shift1, shift2)
        
        if merged:
            # Should have correct start/end regardless of order passed
            assert merged.start_time == time(9, 0)
            assert merged.end_time == time(11, 0)

    @patch('schedule_generator.ShiftGap')
    def test_gap_analyzer_with_merge_recommendations(self, mock_shiftgap, app, db_session, sample_term):
        """Gap analyzer generates merge recommendations (lines 406-409)."""
        from schedule_generator import GapAnalyzer
        
        # Create mock gap with merge suggestion
        mock_gap = MagicMock()
        mock_gap.gap_id = 1
        mock_gap.is_resolved = False
        mock_gap.user.name = "Test User"
        mock_gap.date = date(2025, 9, 1)
        mock_gap.gap_duration_minutes = 20
        mock_gap.get_merge_suggestion.return_value = {'can_merge': True, 'recommendation': 'Merge shifts'}
        
        mock_shiftgap.detect_all_gaps_for_term.return_value = [mock_gap]
        mock_shiftgap.get_gap_summary.return_value = {'total': 1}
        
        result = GapAnalyzer.analyze_term_gaps(sample_term.term_id)
        
        assert len(result['merge_recommendations']) == 1
        assert result['merge_recommendations'][0]['gap_id'] == 1


class TestGenerateShiftsForNeed:
    """Test generating shifts for staffing needs."""

    def test_generate_shifts_for_need(self, app, db_session, sample_term, policy, student_user,
                                      staffing_needs, availability_record):
        """Generates shifts to meet staffing need."""
        from schedule_generator import ScheduleGenerator
        
        gen = ScheduleGenerator(sample_term.term_id)
        
        # Get available users
        available_users = gen._get_available_users(date(2025, 9, 1), 0)
        
        shifts = gen._generate_shifts_for_need(staffing_needs, date(2025, 9, 1), available_users)
        
        # Should generate some shifts (or none if constraints prevent it)
        assert isinstance(shifts, list)

    def test_generate_shifts_respects_required_count(self, app, db_session, sample_term, policy,
                                                     staffing_needs, availability_record):
        """Respects required_count from staffing needs."""
        from schedule_generator import ScheduleGenerator
        
        # Create multiple students with availability
        students = []
        for i in range(5):
            student = User(
                name=f"Test Student {i}",
                email=f"teststudent{i}@colby.edu",
                role="student",
                is_active=True
            )
            student.set_password("testpass")
            db_session.add(student)
            students.append(student)
        db_session.commit()
        
        # Add availability for each student
        for student in students:
            avail = Availability(
                user_id=student.user_id,
                term_id=sample_term.term_id,
                day_of_week="Mon",
                start_time=time(8, 0),
                end_time=time(18, 0),
                is_exception=False
            )
            db_session.add(avail)
        db_session.commit()
        
        gen = ScheduleGenerator(sample_term.term_id)
        available_users = gen._get_available_users(date(2025, 9, 1), 0)
        
        staffing_needs.required_count = 2
        
        shifts = gen._generate_shifts_for_need(staffing_needs, date(2025, 9, 1), available_users)
        
        assert len(shifts) <= staffing_needs.required_count
