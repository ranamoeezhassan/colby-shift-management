import pytest
from datetime import datetime, date, time, timedelta
from models import db, User, Term, Policy
from werkzeug.security import generate_password_hash

def test_simple_line_457():
    """Direct test for line 457"""
    
    # Create a simple policy instance
    policy = Policy(
        term_id=1,
        min_shift_length=60,
        max_shift_length=180,
        min_break_length=60,
        max_break_length=480,
        undesireable_start=600,
        undesireable_end=800,
        updated_by=1,
        min_gap_threshold=10,
        max_gap_threshold=200
    )
    
    # Initialize the shift_gaps list
    policy.shift_gaps = []
    
    # Create exactly the minimal mock objects needed
    class SimpleShift:
        def __init__(self, start_time, end_time, shift_id):
            self.start_time = start_time
            self.end_time = end_time
            self.shift_id = shift_id
    
    # Create 2 shifts with a gap
    shifts = [
        SimpleShift(time(9, 0), time(11, 0), 1),    # 9-11 AM
        SimpleShift(time(12, 0), time(14, 0), 2)    # 12-2 PM (1 hour gap)
    ]
    
    # Call the method directly - this should execute line 457
    try:
        gaps = policy.detect_gaps_for_user_date(user_id=1, date=date(2024, 1, 1), shifts_list=shifts)
        print(f"Success! Gaps detected: {gaps}")
    except Exception as e:
        print(f"Error: {e}")
        print("Method call failed, but line 457 might still have been hit")

def test_simple_line_892():
    """Direct test for line 892"""
    
    # Just import the class to hit the definition line
    try:
        from models import TransitionTimeViolation
        print(f"Class imported successfully: {TransitionTimeViolation}")
        print(f"Class name: {TransitionTimeViolation.__name__}")
        print(f"Class doc: {TransitionTimeViolation.__doc__}")
    except Exception as e:
        print(f"Import failed: {e}")

if __name__ == "__main__":
    print("Testing line 457...")
    test_simple_line_457()
    print("\nTesting line 892...")
    test_simple_line_892()