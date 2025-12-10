"""
Test coverage for constraints/__init__.py
"""
import pytest


class TestConstraintsInit:
    """Tests for constraints blueprint initialization."""

    def test_constraints_blueprint_creation(self):
        """Test that the constraints blueprint is properly created."""
        from blueprints.constraints import constraints_bp
        
        # Test blueprint exists and has correct name
        assert constraints_bp is not None
        assert constraints_bp.name == 'constraints'
        assert constraints_bp.url_prefix == '/constraints'
        
        # Test blueprint has template and static folders configured
        assert hasattr(constraints_bp, 'template_folder')
        assert hasattr(constraints_bp, 'static_folder')
        
    def test_constraints_blueprint_registration(self, app):
        """Test that the blueprint can be registered with an app."""
        from blueprints.constraints import constraints_bp
        
        with app.app_context():
            # Blueprint should be importable and registrable
            assert constraints_bp.name in [bp.name for bp in app.iter_blueprints()]