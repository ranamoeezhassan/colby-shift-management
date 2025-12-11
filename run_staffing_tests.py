#!/usr/bin/env python3
"""
Staffing Needs Test Runner

This script provides an easy way to run all staffing needs tests with different options.

Usage:
    python run_staffing_tests.py                    # Run all tests
    python run_staffing_tests.py --models           # Run only model tests  
    python run_staffing_tests.py --routes           # Run only route tests
    python run_staffing_tests.py --validation       # Run only validation tests
    python run_staffing_tests.py --integration      # Run only integration tests
    python run_staffing_tests.py --coverage         # Run with coverage report
    python run_staffing_tests.py --verbose          # Run with verbose output
"""

import subprocess
import sys
import argparse


def run_tests(test_class=None, verbose=False, coverage=False):
    """Run pytest with specified options"""
    cmd = ["python3", "-m", "pytest"]
    
    # Add test file and class if specified
    if test_class:
        cmd.append(f"tests/test_staffing_needs_focused.py::{test_class}")
    else:
        cmd.append("tests/test_staffing_needs_focused.py")
    
    # Add verbose flag
    if verbose:
        cmd.append("-v")
    
    # Add coverage options
    if coverage:
        cmd.extend(["--cov=models", "--cov=blueprints.staffing", "--cov-report=term-missing"])
    
    # Run the command
    print(f"Running command: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=".")
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="Run staffing needs tests")
    parser.add_argument("--models", action="store_true", help="Run only model tests")
    parser.add_argument("--routes", action="store_true", help="Run only route tests")
    parser.add_argument("--validation", action="store_true", help="Run only validation tests")
    parser.add_argument("--integration", action="store_true", help="Run only integration tests")
    parser.add_argument("--coverage", action="store_true", help="Include coverage report")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    # Determine which test class to run
    test_class = None
    if args.models:
        test_class = "TestStaffingNeedsModel"
    elif args.routes:
        test_class = "TestStaffingRoutesBasic"
    elif args.validation:
        test_class = "TestStaffingValidation"
    elif args.integration:
        test_class = "TestStaffingIntegration"
    
    # Run the tests
    return run_tests(test_class, args.verbose, args.coverage)


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)