# Test Instructions

## Setup

1. Install test dependencies:
```bash
pip install -r requirements-test.txt
```

2. Run the tests:
```bash
pytest
```

## Running Specific Tests

Run specific test files:
```bash
pytest tests/test_database.py
```

Run specific test methods:
```bash
pytest tests/test_database.py::TestDatabaseInitialization::test_user_model_basic_operations
```

Run with verbose output:
```bash
pytest -v
```