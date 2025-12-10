import pytest
from unittest.mock import patch, MagicMock
from flask import json
from models import User, Policy, Term, db
from datetime import date
from blueprints.constraints.routes import validate_policy_data

class TestConstraintsRoutesCoverage:
    
    @pytest.fixture
    def authenticated_client(self, client, app, db_session):
        """Create an authenticated test client with supervisor role."""
        with app.app_context():
            supervisor = User(email='supervisor@test.com', name='Supervisor', role='supervisor')
            supervisor.set_password('password')
            db.session.add(supervisor)
            db.session.commit()
            
        client.post('/login', data={
            'email': 'supervisor@test.com',
            'password': 'password',
            'g-recaptcha-response': 'test'
        }, follow_redirects=True)
        return client

    @pytest.fixture(autouse=True)
    def setup_data(self, app, db_session):
        pass

    def test_create_student_api_success(self, authenticated_client, app, db_session):
        """Test successful student creation."""
        payload = {
            'name': 'New Student',
            'email': 'newstudent@test.com',
            'password': 'password123'
        }
        resp = authenticated_client.post('/constraints/api/students', json=payload)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['student']['email'] == 'newstudent@test.com'
        
        # Verify in DB
        with app.app_context():
            user = User.query.filter_by(email='newstudent@test.com').first()
            assert user is not None
            assert user.role == 'student'

    def test_create_student_api_missing_fields(self, authenticated_client):
        """Test missing fields validation."""
        payload = {'name': 'Incomplete'}
        resp = authenticated_client.post('/constraints/api/students', json=payload)
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert 'required' in data['error']

    def test_create_student_api_duplicate_email(self, authenticated_client, sample_user):
        """Test duplicate email validation."""
        payload = {
            'name': 'Duplicate',
            'email': sample_user.email,
            'password': 'password123'
        }
        resp = authenticated_client.post('/constraints/api/students', json=payload)
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert 'already exists' in data['error']

    def test_create_student_api_access_denied(self, client, app):
        """Test access denied for non-supervisors."""
        # Login as student
        with app.app_context():
            student = User(email='student_access@test.com', name='Student', role='student')
            student.set_password('password')
            db.session.add(student)
            db.session.commit()
            
        client.post('/login', data={'email': 'student_access@test.com', 'password': 'password', 'g-recaptcha-response': 'test'})
        
        payload = {
            'name': 'Another Student',
            'email': 'another@test.com',
            'password': 'password123'
        }
        resp = client.post('/constraints/api/students', json=payload)
        assert resp.status_code == 403
        data = resp.get_json()
        assert data['success'] is False
        assert 'Access denied' in data['error']

    def test_exception_handlers(self, authenticated_client, app, sample_user):
        """Test exception handlers by mocking db.session.commit to raise Exception."""
        
        # 1. update_policy_by_term (287-289)
        # Need existing policy
        with app.app_context():
            t = Term(name='TermEx', start_date=date(2025,1,1), end_date=date(2025,1,31), availability_deadline=date(2024,12,31))
            db.session.add(t)
            db.session.commit()
            tid = t.term_id
            p = Policy(term_id=tid, updated_by=1, min_break_length=15, min_shift_length=60, max_shift_length=120, max_break_length=60, undesireable_start=0, undesireable_end=2359)
            db.session.add(p)
            db.session.commit()
            
        with patch('models.db.session.commit', side_effect=Exception('DB Error')):
             resp = authenticated_client.put(f'/constraints/api/policies/by-term/{tid}', json={'min_shift_length': 60})
             assert resp.status_code == 500
             assert 'DB Error' in resp.get_json()['error']

        # 2. update_term_policy_api (333-335)
        with patch('models.db.session.commit', side_effect=Exception('DB Error 2')):
             resp = authenticated_client.put(f'/constraints/api/terms/{tid}/policy', json={'min_shift_length': 60})
             assert resp.status_code == 500
             assert 'DB Error 2' in resp.get_json()['error']

        # 3. constraints_setup (593-596) - Exception loading preferences
        with patch('models.Policy.query') as mock_query:
            mock_query.all.side_effect = Exception('Pref Error')
            resp = authenticated_client.get('/constraints/setup')
            assert resp.status_code == 200 
            
        # 4. get_current_constraints (675-679)
        # Patch models.Policy.query directly to ensure we catch the access
        with patch('models.Policy.query') as mock_query:
            mock_query.order_by.side_effect = Exception('Status Error')
            resp = authenticated_client.get('/constraints/api/current-constraints')
            assert resp.status_code == 500
            assert 'Status Error' in resp.get_json()['error']

        # 5. create_bulk_validation (734-735)
        with patch('models.Policy.query') as mock_query:
            mock_query.all.side_effect = Exception('Bulk Error')
            resp = authenticated_client.post('/constraints/api/validations/bulk')
            assert resp.get_json()['success'] is False
    
        # 6. create_policy_api (1072-1086)
        with patch('models.db.session.commit', side_effect=Exception('Create Policy Error')):
            payload = {
                'term_id': 999,
                'min_shift_length': 60,
                'max_shift_length': 120,
                'min_break_length': 15,
                'undesireable_start': 600,
                'undesireable_end': 2200
            }
            resp = authenticated_client.post('/constraints/api/policies', json=payload)
            assert resp.status_code == 500
            assert 'Create Policy Error' in resp.get_json()['error']
    
        # 7. update_policy_api (1149)
        # Need existing policy
        with app.app_context():
            p = Policy(term_id=tid, updated_by=1, min_break_length=15, min_shift_length=60, max_shift_length=120, max_break_length=60, undesireable_start=0, undesireable_end=2359) # Reuse term
            db.session.add(p)
            db.session.commit()
            pid = p.policy_id
    
        with patch('models.db.session.commit', side_effect=Exception('Update Policy Error')):
            resp = authenticated_client.put(f'/constraints/api/policies/{pid}', json={'min_shift_length': 60})
            assert resp.status_code == 500
            assert 'Update Policy Error' in resp.get_json()['error']

        # 8. get_terms_api (1179)
        with patch('models.Term.query') as mock_query:
            mock_query.all.side_effect = Exception('Get Terms Error')
            resp = authenticated_client.get('/constraints/api/terms')
            assert resp.status_code == 200
            assert resp.get_json()['success'] is False

        # 9. list_students_api (1209-1210)
        with patch('models.User.query') as mock_query:
            mock_query.filter_by.side_effect = Exception('List Students Error')
            resp = authenticated_client.get('/constraints/api/students')
            assert resp.status_code == 500

        # 10. create_student_api exception (1263-1264)
        with patch('models.db.session.commit', side_effect=Exception('Create Student Error')):
            payload = {
                'name': 'Error Student',
                'email': 'error@test.com',
                'password': 'password'
            }
            resp = authenticated_client.post('/constraints/api/students', json=payload)
            assert resp.status_code == 500

        # 11. update_student_api (1310-1312)
        # Need existing student
        with app.app_context():
            s = User(email='update@test.com', name='Update', role='student')
            s.set_password('password')
            db.session.add(s)
            db.session.commit()
            sid = s.user_id
            
        with patch('models.db.session.commit', side_effect=Exception('Update Student Error')):
            resp = authenticated_client.put(f'/constraints/api/students/{sid}', json={'name': 'New Name'})
            assert resp.status_code == 500

        # 12. delete_student_api (1337-1339)
        with patch('models.db.session.commit', side_effect=Exception('Delete Student Error')):
            resp = authenticated_client.delete(f'/constraints/api/students/{sid}')
            assert resp.status_code == 500

    def test_validate_policy_data_via_api(self, authenticated_client):
        """Test validate_policy_data logic via API to ensure coverage."""
        
        # min_shift >= max_shift (474)
        payload = {
            'term_id': 1,
            'min_shift_length': 120,
            'max_shift_length': 120,
            'min_break_length': 15,
            'undesireable_start': 600,
            'undesireable_end': 2200
        }
        resp = authenticated_client.post('/constraints/api/policies', json=payload)
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert 'Minimum shift length must be less than maximum shift length' in data['error']

        # min_shift > max_shift
        payload['min_shift_length'] = 130
        resp = authenticated_client.post('/constraints/api/policies', json=payload)
        assert resp.status_code == 400
        assert 'Minimum shift length must be less than maximum shift length' in resp.get_json()['error']

    def test_bulk_validation_logic(self, authenticated_client, app):
        """Test bulk validation logic for lines 720-725."""
        with app.app_context():
            # Create policies that trigger the warnings
            # Need unique term_ids
            p1 = Policy(term_id=201, min_shift_length=20, max_shift_length=60, updated_by=1, min_break_length=15, max_break_length=30, undesireable_start=0, undesireable_end=2400) # Too short
            p2 = Policy(term_id=202, min_shift_length=60, max_shift_length=500, updated_by=1, min_break_length=15, max_break_length=30, undesireable_start=0, undesireable_end=2400) # Too long
            p3 = Policy(term_id=203, min_shift_length=100, max_shift_length=100, updated_by=1, min_break_length=15, max_break_length=30, undesireable_start=0, undesireable_end=2400) # Min >= Max
            db.session.add_all([p1, p2, p3])
            db.session.commit()
            
        resp = authenticated_client.post('/constraints/api/validations/bulk')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['violations'] >= 3
        results = str(data['results'])
        assert 'Min shift length too short' in results
        assert 'Max shift length too long' in results
        assert 'Min shift length >= Max shift length' in results

    def test_update_constraints_configuration_value_error(self, authenticated_client, app):
        """Test ValueError in update_constraints_configuration (821)."""
        # Need to trigger ValueError when parsing custom_start_time
        payload = {
            'custom_start_time': 'invalid',
            'custom_end_time': 'invalid'
        }
        resp = authenticated_client.put('/constraints/api/configurations', json=payload)
        assert resp.status_code == 200

    def test_student_management_route(self, authenticated_client):
        """Test student management route explicitly."""
        resp = authenticated_client.get('/constraints/students')
        assert resp.status_code == 200

    def test_get_terms_api_success(self, authenticated_client, app):
        """Test get_terms_api success path."""
        with app.app_context():
            t = Term(name='TermSuccess', start_date=date(2025,1,1), end_date=date(2025,1,31), availability_deadline=date(2024,12,31))
            db.session.add(t)
            db.session.commit()
            
        resp = authenticated_client.get('/constraints/api/terms')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert len(data['terms']) >= 1

    def test_validate_policy_data_direct(self):
        """Directly test validate_policy_data to force coverage."""
        # Valid data
        data = {
            'term_id': 1,
            'min_shift_length': 60,
            'max_shift_length': 240,
            'min_break_length': 15,
            'max_break_length': 60,
            'undesireable_start': 600,
            'undesireable_end': 2200
        }
        assert validate_policy_data(data)['valid'] is True

        # Invalid: min >= max
        data['min_shift_length'] = 240
        assert validate_policy_data(data)['valid'] is False
        
        # Invalid: min_break < 0
        data['min_shift_length'] = 60
        data['min_break_length'] = -1
        assert validate_policy_data(data)['valid'] is False
        
        # Invalid: max_break < min_break
        data['min_break_length'] = 15
        data['max_break_length'] = 10
        assert validate_policy_data(data)['valid'] is False
        
        # Invalid: max_break > 1440
        data['max_break_length'] = 1500
        assert validate_policy_data(data)['valid'] is False
        
        # Invalid: undesireable_start < 0
        data['max_break_length'] = 60
        data['undesireable_start'] = -1
        assert validate_policy_data(data)['valid'] is False
        
        # Invalid: undesireable_end > 2359
        data['undesireable_start'] = 600
        data['undesireable_end'] = 2400
        assert validate_policy_data(data)['valid'] is False

    def test_validate_policy_data_min_ge_max(self):
        """Test validate_policy_data when min_shift >= max_shift (Line 474)"""
        data = {
            'term_id': 1,
            'min_shift_length': 120,
            'max_shift_length': 120,  # Equal
            'min_break_length': 15,
            'undesireable_start': 600,
            'undesireable_end': 2200
        }
        result = validate_policy_data(data)
        assert result['valid'] is False
        assert 'Minimum shift length must be less than maximum shift length' in result['error']

        data['min_shift_length'] = 130 # Greater
        result = validate_policy_data(data)
        assert result['valid'] is False
        assert 'Minimum shift length must be less than maximum shift length' in result['error']

    def test_validate_policy_data_limits(self):
        """Test validate_policy_data limits (Lines 474, 476)"""
        data = {
            'term_id': 1,
            'min_shift_length': 250, # > 240
            'max_shift_length': 300,
            'min_break_length': 15,
            'undesireable_start': 600,
            'undesireable_end': 2200
        }
        result = validate_policy_data(data)
        assert result['valid'] is False
        assert 'Minimum shift length cannot exceed 4 hours' in result['error']

        data['min_shift_length'] = 60
        data['max_shift_length'] = 50 # < 60
        result = validate_policy_data(data)
        assert result['valid'] is False
        assert 'Maximum shift length cannot be less than 1 hour' in result['error']

    def test_get_current_constraints_exception(self, authenticated_client):
        """Test exception handler in get_current_constraints (Lines 676-680)"""
        with patch('models.Policy.query') as mock_query:
            mock_query.order_by.side_effect = Exception("DB Error")
            resp = authenticated_client.get('/constraints/api/current-constraints')
            assert resp.status_code == 500
            data = resp.get_json()
            assert data['success'] is False
            assert 'DB Error' in data['error']

    def test_create_policy_api_exception(self, authenticated_client):
        """Test exception handler in create_policy_api (Line 1089)"""
        payload = {
            'term_id': 1,
            'min_shift_length': 60,
            'max_shift_length': 120,
            'min_break_length': 15,
            'undesireable_start': 600,
            'undesireable_end': 2200
        }
        with patch('blueprints.constraints.routes.validate_policy_data') as mock_validate:
            mock_validate.return_value = {'valid': True}
            with patch('models.db.session.commit') as mock_commit:
                mock_commit.side_effect = Exception("Commit Error")
                resp = authenticated_client.post('/constraints/api/policies', json=payload)
                assert resp.status_code == 500
                data = resp.get_json()
                assert data['success'] is False
                assert 'Commit Error' in data['error']

    def test_update_policy_api_exception(self, authenticated_client, app):
        """Test exception handler in update_policy_api (Line 1168)"""
        # Create a policy first
        with app.app_context():
            term = Term(name='TermUpdate', start_date=date(2025,2,1), end_date=date(2025,2,28), availability_deadline=date(2025,1,31))
            db.session.add(term)
            db.session.commit()
            policy = Policy(
                term_id=term.term_id, 
                min_shift_length=60, 
                max_shift_length=120, 
                min_break_length=15,
                max_break_length=60,
                undesireable_start=600,
                undesireable_end=2200,
                updated_by=1
            )
            db.session.add(policy)
            db.session.commit()
            policy_id = policy.policy_id

        payload = {'min_shift_length': 90}
        with patch('models.db.session.commit') as mock_commit:
            mock_commit.side_effect = Exception("Update Error")
            resp = authenticated_client.put(f'/constraints/api/policies/{policy_id}', json=payload)
            assert resp.status_code == 500
            data = resp.get_json()
            assert data['success'] is False
            assert 'Update Error' in data['error']
