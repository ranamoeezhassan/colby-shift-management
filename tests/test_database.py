import pytest
from models import db, User, Term, Availability, StaffingNeeds
from datetime import date, time


class TestDatabaseInitialization:
    """Test database initialization and basic functionality."""
    
    def test_database_tables_created(self, app, db_session):
        """Test that all database tables are created properly."""
        with app.app_context():
            # Check that tables exist by querying their metadata
            inspector = db.inspect(db.engine)
            table_names = inspector.get_table_names()
            print(f"Available tables: {table_names}")
            
            # Verify core tables exist
            assert 'users' in table_names
            assert 'terms' in table_names
            assert 'availability' in table_names
            assert 'staffing_needs' in table_names
    
    def test_user_model_basic_operations(self, app, db_session):
        """Test basic User model CRUD operations."""
        with app.app_context():
            # Test user creation
            user = User(
                name='Jane Doe',
                email='jane@colby.edu',
                role='supervisor',
                is_active=True
            )
            user.set_password('securepass')
            
            db.session.add(user)
            db.session.commit()
            
            # Test user retrieval
            retrieved_user = User.query.filter_by(email='jane@colby.edu').first()
            assert retrieved_user is not None
            assert retrieved_user.name == 'Jane Doe'
            assert retrieved_user.role == 'supervisor'
            assert retrieved_user.is_active is True
            assert retrieved_user.check_password('securepass') is True
            assert retrieved_user.check_password('wrongpass') is False
            
            # Test user update
            retrieved_user.role = 'manager'
            db.session.commit()
            
            updated_user = User.query.filter_by(email='jane@colby.edu').first()
            assert updated_user.role == 'manager'
            
            # Test user deletion
            db.session.delete(updated_user)
            db.session.commit()
            
            deleted_user = User.query.filter_by(email='jane@colby.edu').first()
            assert deleted_user is None
    
    def test_term_model_basic_operations(self, app, db_session):
        """Test basic Term model CRUD operations."""
        with app.app_context():
            # Test term creation
            term = Term(
                name='Spring 2026',
                start_date=date(2026, 1, 15),
                end_date=date(2026, 5, 15),
                availability_deadline=date(2026, 1, 1),
                locked=False
            )
            
            db.session.add(term)
            db.session.commit()
            
            # Test term retrieval
            retrieved_term = Term.query.filter_by(name='Spring 2026').first()
            assert retrieved_term is not None
            assert retrieved_term.start_date == date(2026, 1, 15)
            assert retrieved_term.end_date == date(2026, 5, 15)
            assert retrieved_term.locked is False
            
            # Test term update
            retrieved_term.locked = True
            db.session.commit()
            
            updated_term = Term.query.filter_by(name='Spring 2026').first()
            assert updated_term.locked is True
    
    def test_availability_model_basic_operations(self, app, db_session, sample_user, sample_term):
        """Test basic Availability model CRUD operations."""
        with app.app_context():
            # Use the fixture data
            user = sample_user
            term = sample_term
            
            assert user is not None
            assert term is not None
            
            # Test availability creation
            availability = Availability(
                user_id=user.user_id,
                term_id=term.term_id,
                day_of_week='Monday',
                start_time=time(9, 0),
                end_time=time(17, 0)
            )
            
            db.session.add(availability)
            db.session.commit()
            
            # Test availability retrieval
            retrieved_availability = Availability.query.filter_by(
                user_id=user.user_id,
                day_of_week='Monday'
            ).first()
            
            assert retrieved_availability is not None
            assert retrieved_availability.start_time == time(9, 0)
            assert retrieved_availability.end_time == time(17, 0)
            assert retrieved_availability.user.email == 'test@colby.edu'
            assert retrieved_availability.term.name == 'Fall 2025'
    
    def test_staffing_needs_model_basic_operations(self, app, db_session, sample_term):
        """Test basic StaffingNeeds model CRUD operations."""
        with app.app_context():
            # Use the fixture data
            term = sample_term
            
            # Test staffing need creation
            staffing_need = StaffingNeeds(
                term_id=term.term_id,
                day_of_week=0,  # Monday
                start_time=time(10, 0),
                end_time=time(14, 0),
                role_required='student',
                required_count=2
            )
            
            db.session.add(staffing_need)
            db.session.commit()
            
            # Test staffing need retrieval
            retrieved_need = StaffingNeeds.query.filter_by(
                term_id=term.term_id,
                day_of_week=0
            ).first()
            
            assert retrieved_need is not None
            assert retrieved_need.start_time == time(10, 0)
            assert retrieved_need.end_time == time(14, 0)
            assert retrieved_need.role_required == 'student'
            assert retrieved_need.required_count == 2
            assert retrieved_need.term.name == 'Fall 2025'
    
    def test_database_relationships(self, app, db_session, sample_user, sample_term):
        """Test database relationships work correctly."""
        with app.app_context():
            # Use fixture data
            user = sample_user
            term = sample_term
            
            # Create availability record
            availability = Availability(
                user_id=user.user_id,
                term_id=term.term_id,
                day_of_week='Tuesday',
                start_time=time(8, 0),
                end_time=time(16, 0)
            )
            db.session.add(availability)
            
            # Create staffing need
            staffing_need = StaffingNeeds(
                term_id=term.term_id,
                day_of_week=1,  # Tuesday
                start_time=time(9, 0),
                end_time=time(15, 0),
                role_required='student',
                required_count=1
            )
            db.session.add(staffing_need)
            db.session.commit()
            
            # Test relationships
            # User -> Availability
            user_availabilities = user.availability
            assert len(user_availabilities) > 0
            assert any(av.day_of_week == 'Tuesday' for av in user_availabilities)
            
            # Term -> Availability
            term_availabilities = term.availability
            assert len(term_availabilities) > 0
            
            # Term -> StaffingNeeds
            term_staffing_needs = term.staffing_needs
            assert len(term_staffing_needs) > 0
            assert any(sn.day_of_week == 1 for sn in term_staffing_needs)
    
    def test_database_constraints(self, app, db_session):
        """Test database constraints and validation."""
        with app.app_context():
            # Test unique email constraint
            user1 = User(
                name='User One',
                email='duplicate@colby.edu',
                role='student',
                is_active=True
            )
            user1.set_password('pass1')
            
            user2 = User(
                name='User Two',
                email='duplicate@colby.edu',
                role='supervisor',
                is_active=True
            )
            user2.set_password('pass2')
            
            db.session.add(user1)
            db.session.commit()
            
            # Adding second user with same email should fail
            db.session.add(user2)
            with pytest.raises(Exception):  # Should raise IntegrityError
                db.session.commit()
            
            # Rollback the failed transaction
            db.session.rollback()
    
    def test_password_hashing(self, app, db_session, sample_user):
        """Test password hashing functionality."""
        with app.app_context():
            user = sample_user
            
            # Test that password is hashed
            assert user.password_hash != 'testpass'
            
            # Test password checking
            assert user.check_password('testpass') is True
            assert user.check_password('wrongpass') is False
            
            # Test password change
            user.set_password('newpass')
            db.session.commit()
            
            assert user.check_password('newpass') is True
            assert user.check_password('testpass') is False