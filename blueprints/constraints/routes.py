from flask import render_template, request, redirect, url_for, flash, jsonify, send_file, make_response, abort
from flask_login import login_required, current_user
from . import constraints_bp
from models import db, Policy, UndesirableTimeWindow, Term, User, Shift, ShiftViolation, ShiftGap
from cache import cache, outputs_index_key
# Note: UndesirableShiftTracking, RejectedShift, SplitShift, PolicyAuditLog, ValidationReport 
# are now compatibility wrappers - data stored in Policy JSON fields
from datetime import time, date, datetime
from schedule_generator import ScheduleGenerator
from utils.pdf_generator import generate_validation_pdf

# GitHub Issues #21-37: Constraints & Equity
# Features: Shift duration, gaps, policy management, etc.

def get_request_data():
    """Helper function to get data from either JSON or form"""
    if request.is_json:
        return request.get_json() or {}
    else:
        return request.form.to_dict()

@constraints_bp.route('/validation-dashboard')
@login_required
def validation_dashboard():
    """Unified validation dashboard combining reports and alerts"""
    terms = Term.query.all()
    
    # Get recent validation activity - simplified for now
    recent_activity = []
    
    # Get violation summary stats
    violation_summary = {
        'total_violations': 0,
        'by_severity': {'critical': 0, 'major': 0, 'minor': 0},
        'by_type': {'duration': 0, 'gap': 0, 'transition': 0}
    }
    
    return render_template('validation_dashboard.html',
                         terms=terms,
                         recent_activity=recent_activity,
                         violation_summary=violation_summary)

@constraints_bp.route('/')
@login_required
def index():
    return render_template('constraints_index.html')



# Issue #14: Policy Configuration Routes



@constraints_bp.route('/api/policies', methods=['GET'])
@login_required  
def get_policies_api():
    """Get all policies in JSON format"""
    try:
        term_id = request.args.get('term_id', type=int)
        
        query = Policy.query
        if term_id:
            query = query.filter_by(term_id=term_id)
            
        policies = query.all()
        
        policies_data = []
        for policy in policies:
            policy_dict = {
                'policy_id': policy.policy_id,
                'term_id': policy.term_id,
                'term_name': policy.term.name if policy.term else 'Unknown',
                'min_shift_length': policy.min_shift_length,
                'max_shift_length': policy.max_shift_length,
                'min_break_length': policy.min_break_length,
                'max_break_length': policy.max_break_length,
                'undesirable_start': policy.undesireable_start,
                'undesirable_end': policy.undesireable_end,
                'updated_by': policy.updated_by
            }
            policies_data.append(policy_dict)
        
        return jsonify({
            'success': True,
            'policies': policies_data,
            'count': len(policies_data)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



@constraints_bp.route('/api/policies/<int:policy_id>', methods=['DELETE'])
@login_required
def delete_policy_api(policy_id):
    """Delete a policy with audit logging"""
    from models import PolicyAuditLog
    
    try:
        policy = db.session.get(Policy, policy_id)
        if not policy:
            return jsonify({'success': False, 'error': 'Policy not found'}), 404
        
        # Check if there are any shifts associated with this policy's term
        associated_shifts = Shift.query.filter_by(term_id=policy.term_id).count()
        if associated_shifts > 0:
            return jsonify({
                'success': False, 
                'error': f'Cannot delete policy: {associated_shifts} shifts are associated with this term'
            }), 409
        
        # Create audit log entry before deletion
        PolicyAuditLog.log_policy_change(
            policy_id=policy.policy_id,
            changed_by_id=current_user.user_id,
            change_type='delete',
            change_reason='Policy deleted',
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        
        db.session.delete(policy)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Policy {policy_id} deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# REST API endpoints for Undesirable Windows


# REST API endpoints for Volunteer Preferences  
@constraints_bp.route('/api/volunteer-preferences', methods=['GET'])
@login_required
def get_volunteer_preferences_api():
    """Get all volunteer preferences"""
    try:
        # Get preferences from policy JSON instead of separate table
        preferences_data = []
        policies = Policy.query.all()
        
        for policy in policies:
            if policy.volunteer_preferences:
                for pref in policy.volunteer_preferences.get('preferences', []):
                    user = db.session.get(User, pref.get('user_id'))
                    preferences_data.append({
                        'preference_id': pref.get('preference_id'),
                        'user_id': pref.get('user_id'),
                        'user_name': user.name if user else 'Unknown',
                        'preference_type': pref.get('preference_type'),
                        'is_volunteer': pref.get('is_volunteer', True),
                        'notes': pref.get('notes'),
                        'created_at': pref.get('created_at')
                    })
        
        return jsonify({'success': True, 'preferences': preferences_data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@constraints_bp.route('/api/volunteer-preferences', methods=['POST'])
@login_required
def create_volunteer_preference_api():
    """Create a new volunteer preference"""
    try:
        data = request.get_json()
        
        # Use consolidated policy storage for volunteer preferences
        policy = Policy.query.first()  # Get any policy or create default
        if not policy:
            # Create a default policy if none exists
            policy = Policy(
                term_id=1,  # Default term
                **Policy.get_default_values(),
                updated_by=current_user.user_id
            )
            db.session.add(policy)
        
        if not policy.volunteer_preferences:
            policy.volunteer_preferences = {'preferences': []}
        
        # Check if preference already exists
        existing = any(p.get('user_id') == data['user_id'] and p.get('preference_type') == data['preference_type'] 
                      for p in policy.volunteer_preferences.get('preferences', []))
        
        if existing:
            return jsonify({'success': False, 'error': 'Preference already exists for this student and type'}), 400
        
        preference_data = {
            'preference_id': len(policy.volunteer_preferences.get('preferences', [])) + 1,
            'user_id': data['user_id'],
            'preference_type': data['preference_type'],
            'is_volunteer': True,
            'notes': data.get('notes', ''),
            'created_by': current_user.user_id,
            'created_at': datetime.now().isoformat()
        }
        
        policy.volunteer_preferences['preferences'].append(preference_data)
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(policy, 'volunteer_preferences')
        db.session.commit()
        
        return jsonify({
            'success': True,
            'preference_id': preference_data['preference_id'],
            'message': 'Volunteer preference added successfully'
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@constraints_bp.route('/api/volunteer-preferences/<int:preference_id>', methods=['DELETE'])
@login_required
def delete_volunteer_preference_api(preference_id):
    """Delete a volunteer preference"""
    try:
        # Find and remove preference from policy JSON
        policy = Policy.query.first()
        if not policy or not policy.volunteer_preferences:
            return jsonify({'success': False, 'error': 'Preference not found'}), 404
        
        preferences = policy.volunteer_preferences.get('preferences', [])
        updated_preferences = [p for p in preferences if p.get('preference_id') != preference_id]
        
        if len(updated_preferences) == len(preferences):
            return jsonify({'success': False, 'error': 'Preference not found'}), 404
        
        policy.volunteer_preferences['preferences'] = updated_preferences
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(policy, 'volunteer_preferences')
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# REST API endpoints for Validation Operations


# REST API endpoints for Gap Management
@constraints_bp.route('/api/policies/by-term/<int:term_id>', methods=['PUT'])
@login_required
def update_policy_by_term(term_id):
    """Update policy for a specific term."""
    if current_user.role == 'student':
        return {'success': False, 'error': 'Access denied'}, 403
    
    try:
        policy = Policy.query.filter_by(term_id=term_id).first()
        if not policy:
            return {'success': False, 'error': 'Policy not found'}, 404
        
        data = request.get_json()
        
        # Update policy fields
        if 'min_shift_length' in data:
            policy.min_shift_length = data['min_shift_length']
        if 'max_shift_length' in data:
            policy.max_shift_length = data['max_shift_length']
        if 'min_break_length' in data:
            policy.min_break_length = data['min_break_length']
        if 'max_break_length' in data:
            policy.max_break_length = data['max_break_length']
        if 'undesireable_start' in data:
            policy.undesireable_start = data['undesireable_start']
        if 'undesireable_end' in data:
            policy.undesireable_end = data['undesireable_end']
        
        policy.updated_by = current_user.user_id
        db.session.commit()
        
        return {
            'success': True,
            'message': 'Policy updated successfully',
            'policy': {
                'policy_id': policy.policy_id,
                'term_id': policy.term_id,
                'min_shift_length': policy.min_shift_length,
                'max_shift_length': policy.max_shift_length
            }
        }
    except Exception as e:
        db.session.rollback()
        return {'success': False, 'error': str(e)}, 500

@constraints_bp.route('/api/terms/<int:term_id>/policy', methods=['PUT'])
@login_required
def update_term_policy_api(term_id):
    """Update policy settings by term ID"""
    try:
        data = request.get_json()
        
        policy = Policy.query.filter_by(term_id=term_id).first()
        if not policy:
            return jsonify({'success': False, 'error': 'Policy not found for this term'}), 404
        
        # Update policy settings
        if 'min_shift_length' in data:
            policy.min_shift_length = data['min_shift_length']
        if 'max_shift_length' in data:
            policy.max_shift_length = data['max_shift_length']
        if 'min_break_length' in data:
            policy.min_break_length = data['min_break_length']
        if 'max_break_length' in data:
            policy.max_break_length = data['max_break_length']
        
        policy.updated_by = current_user.user_id
        
        # Create audit log entry
        from models import PolicyAuditLog
        PolicyAuditLog.log_policy_change(
            policy_id=policy.policy_id,
            changed_by_id=current_user.user_id,
            change_type='update',
            change_reason=data.get('change_reason', 'Gap management policy update'),
            old_values=str(policy.__dict__),
            new_values=str(data),
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Policy updated successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@constraints_bp.route('/volunteer-preferences')
@login_required
def volunteer_preferences():
    """Display volunteer preferences management for early/late shifts"""
    
    terms = Term.query.all()
    users = User.query.filter_by(is_active=True).all()
    
    # Get volunteer preferences from policy JSON field
    preferences = []
    policies = Policy.query.all()
    for policy in policies:
        if policy.volunteer_preferences:
            preferences.extend(policy.volunteer_preferences.get('preferences', []))
    
    return render_template('volunteer_preferences.html',
                         terms=terms,
                         users=users, 
                         preferences=preferences)

# Issue #26: Shift Duration Validation Routes

@constraints_bp.route('/api/validations/shift', methods=['POST'])
@login_required
def create_shift_validation():
    """Create a new shift validation against policy constraints (Issue #26)"""
    data = request.get_json()
    
    try:
        from datetime import time
        
        term_id = data['term_id']
        start_time_str = data['start_time']  # Format: "HH:MM"
        end_time_str = data['end_time']      # Format: "HH:MM"
        
        # Parse time strings
        start_hour, start_min = map(int, start_time_str.split(':'))
        end_hour, end_min = map(int, end_time_str.split(':'))
        
        start_time = time(start_hour, start_min)
        end_time = time(end_hour, end_min)
        
        # Validate using Policy enforcement
        is_valid, error_message, policy = Policy.enforce_duration_constraints(
            term_id, start_time, end_time
        )
        
        response_data = {
            'valid': is_valid,
            'message': error_message,
        }
        
        if policy:
            response_data['policy'] = {
                'min_duration': policy.min_shift_length,
                'max_duration': policy.max_shift_length
            }
        print(f"DEBUG: response_data={response_data}")
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({
            'valid': False,
            'message': f'Validation error: {str(e)}'
        }), 400

@constraints_bp.route('/shift-constraints/<int:term_id>')
@login_required
def shift_constraints(term_id):
    """Get shift constraints for a specific term (legacy endpoint for compatibility)."""
    # Redirect to the new REST endpoint
    return redirect(url_for('constraints.get_term_constraints_api', term_id=term_id))

@constraints_bp.route('/api/terms/<int:term_id>/constraints', methods=['GET'])
@login_required
def get_term_constraints_api(term_id):
    """Get shift duration constraints for a specific term (Issue #26)"""
    policy = Policy.get_policy_for_term(term_id)
    
    if not policy:
        return jsonify({
            'success': False,
            'error': f'No policy found for term {term_id}'
        }), 404
    
    return jsonify({
        'success': True,
        'constraints': {
            'min_shift_length': policy.min_shift_length,
            'max_shift_length': policy.max_shift_length,
            'min_break_length': policy.min_break_length,
            'max_break_length': policy.max_break_length,
            'term_id': term_id,
            'term_name': policy.term.name if policy.term else None
        }
    })



# Issue #27: Automatic Rejection System Routes



# Issue #29: Admin Panel for Shift Duration Policies




# Issue #30: Shift Duration Violation Detection and Visual Alerts






def validate_policy_data(data):
    """Validate policy data for reasonable values (Issue #29)"""
    errors = []
    
    # Required fields
    required_fields = ['term_id', 'min_shift_length', 'max_shift_length', 
                      'min_break_length', 'undesireable_start', 'undesireable_end']
    
    for field in required_fields:
        if field not in data or data[field] is None:
            errors.append(f'Field {field} is required')
    
    if errors:
        return {'valid': False, 'error': '; '.join(errors)}
    
    # Validate shift lengths
    min_shift = int(data['min_shift_length'])
    max_shift = int(data['max_shift_length'])
    
    if min_shift < 30:
        errors.append('Minimum shift length cannot be less than 30 minutes')
    if min_shift > 240:
        errors.append('Minimum shift length cannot exceed 4 hours (240 minutes)')
    if max_shift < 60:
        errors.append('Maximum shift length cannot be less than 1 hour (60 minutes)')
    if max_shift > 480:
        errors.append('Maximum shift length cannot exceed 8 hours (480 minutes)')
    if min_shift >= max_shift:
        print("DEBUG: validate_policy_data check")
        errors.append('Minimum shift length must be less than maximum shift length')
    
    # Validate break lengths
    min_break = int(data['min_break_length'])
    if 'max_break_length' in data:
        max_break = int(data['max_break_length'])
        if min_break < 0:
            errors.append('Minimum break length cannot be negative')
        if max_break < min_break:
            errors.append('Maximum break length must be greater than minimum break length')
        if max_break > 1440:  # 24 hours
            errors.append('Maximum break length cannot exceed 24 hours (1440 minutes)')
    
    # Validate undesirable times
    undesireable_start = int(data['undesireable_start'])
    undesireable_end = int(data['undesireable_end'])
    
    if undesireable_start < 0 or undesireable_start > 2359:
        errors.append('Undesirable start time must be between 0000 and 2359')
    if undesireable_end < 0 or undesireable_end > 2359:
        errors.append('Undesirable end time must be between 0000 and 2359')
    
    if errors:
        return {'valid': False, 'error': '; '.join(errors)}
    
    return {'valid': True}






# Issue #31: Validation Summary Report Routes










# Issue #32: Gap Management Routes - Avoid fragmented 15-30 minute slots
















# Issue #35: Minimum break time between shifts - Transition Time Violation Routes






# New simplified constraints interface routes

@constraints_bp.route('/setup')
@login_required
def constraints_setup():
    """Render the new simplified constraints setup wizard"""
    from models import Term, User
    
    # Get actual terms from database
    terms = Term.query.all()
    
    # Get users for volunteer selection
    users = User.query.filter_by(role='student').all()
    
    # Get volunteer preferences from policy JSON field
    try:
        # Organize preferences by type
        volunteer_preferences = {
            'early_morning': [],
            'late_evening': [],
            'weekend': []
        }
        
        policies = Policy.query.all()
        for policy in policies:
            if policy.volunteer_preferences:
                for pref in policy.volunteer_preferences.get('preferences', []):
                    if pref.get('preference_type') in volunteer_preferences and pref.get('is_volunteer'):
                        user = db.session.get(User, pref.get('user_id'))
                        if user:
                            volunteer_preferences[pref.get('preference_type')].append({
                                'user_id': pref.get('user_id'),
                                'name': user.name,
                                'email': user.email
                            })
        
        # Remove duplicates (in case student has multiple entries for same type)
        for pref_type in volunteer_preferences:
            seen_users = set()
            unique_volunteers = []
            for volunteer in volunteer_preferences[pref_type]:
                if volunteer['user_id'] not in seen_users:
                    unique_volunteers.append(volunteer)
                    seen_users.add(volunteer['user_id'])
            volunteer_preferences[pref_type] = unique_volunteers
            
    except Exception as e:
        print(f"Error loading volunteer preferences: {e}")
        # Fallback to empty preferences if there's an error
        volunteer_preferences = {
            'early_morning': [],
            'late_evening': [],
            'weekend': []
        }
    
    return render_template('constraints_setup.html', 
                         terms=terms, 
                         users=users,
                         volunteer_preferences=volunteer_preferences)

@constraints_bp.route('/api/stats')
@login_required
def get_constraints_stats():
    """Get minimal statistics for status panel: policies count and constraints saved.

    constraints_saved is a derived count of configured elements:
      - Each Policy counts as 1 base item
      - Within each Policy we count present fields (min/max shift, break length, undesireable start/end)
      - Each enabled flag in undesirable_windows (weekends_blocked, holidays_blocked) counts
      - Each volunteer preference row counts as 1
    This provides a simple aggregate of how much constraint data exists.
    """
    try:
        from models import Policy

        policies = Policy.query.all()
        policies_count = len(policies)

        # Base count starts with number of policies
        constraints_saved = policies_count

        for p in policies:
            # Count non-null core fields
            if p.min_shift_length: constraints_saved += 1
            if p.max_shift_length: constraints_saved += 1
            if p.min_break_length: constraints_saved += 1
            if p.undesireable_start: constraints_saved += 1
            if p.undesireable_end: constraints_saved += 1
            # Count undesirable window flags
            if p.undesirable_windows:
                if p.undesirable_windows.get('weekends_blocked'): constraints_saved += 1
                if p.undesirable_windows.get('holidays_blocked'): constraints_saved += 1
            # Count volunteer preferences from JSON
            if p.volunteer_preferences:
                volunteer_count = len(p.volunteer_preferences.get('preferences', []))
                constraints_saved += volunteer_count

        return jsonify({'success': True,
                        'policies_count': policies_count,
                        'constraints_saved': constraints_saved})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@constraints_bp.route('/api/current-constraints', methods=['GET'])
@login_required
def get_current_constraints():
    """Get currently saved (latest) constraint configuration"""
    try:
        # Always pick latest policy by primary key (policy_id) for recency
        policy = Policy.query.order_by(Policy.policy_id.desc()).first()
        
        if not policy:
            return jsonify({
                'success': True,
                'has_constraints': False,
                'message': 'No constraints configured yet'
            })
        
        # Get volunteer preferences from policy JSON
        volunteer_summary = {
            'early_morning': [],
            'late_evening': [],
            'weekend': []
        }
        
        volunteer_count = 0
        if policy.volunteer_preferences:
            for pref in policy.volunteer_preferences.get('preferences', []):
                pref_type = pref.get('preference_type')
                user_id = pref.get('user_id')
                if pref_type in volunteer_summary and pref.get('is_volunteer'):
                    volunteer_summary[pref_type].append(user_id)
                    volunteer_count += 1
        
        return jsonify({
            'success': True,
            'has_constraints': True,
            'policy': {
                'policy_id': policy.policy_id,
                'term_id': policy.term_id,
                'min_shift_length': policy.min_shift_length,
                'max_shift_length': policy.max_shift_length,
                'min_break_length': policy.min_break_length,
                'undesireable_start': policy.undesireable_start,
                'undesireable_end': policy.undesireable_end,
                'undesirable_windows': policy.undesirable_windows or {},
                'volunteer_preferences': policy.volunteer_preferences or {}
            },
            'volunteers': volunteer_summary,
            'volunteer_count': volunteer_count
        })
    except Exception as e:
        print(f"DEBUG: Exception caught in get_current_constraints: {e}")
        response = jsonify({'success': False, 'error': str(e)})
        return response, 500

@constraints_bp.route('/api/validations/bulk', methods=['POST'])
@login_required
def create_bulk_validation():
    """Validate all constraints and policies"""
    try:
        from models import Policy
        
        violations_found = 0
        validation_results = []
        
        # Validate all policies
        policies = Policy.query.all()
        for policy in policies:
            # Basic validation checks
            if policy.min_shift_length >= policy.max_shift_length:
                violations_found += 1
                validation_results.append(f"Policy {policy.policy_id}: Min shift length >= Max shift length")
            
            if policy.min_shift_length < 30:  # Less than 30 minutes
                violations_found += 1
                validation_results.append(f"Policy {policy.policy_id}: Min shift length too short")
            
            if policy.max_shift_length > 480:  # More than 8 hours
                violations_found += 1
                validation_results.append(f"Policy {policy.policy_id}: Max shift length too long")
        
        return jsonify({
            'success': True,
            'violations': violations_found,
            'results': validation_results,
            'message': f'Validation complete. Found {violations_found} violations.',
            'redirect_url': url_for('constraints.validation_reports') if violations_found > 0 else None
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@constraints_bp.route('/validation-reports/generate', methods=['POST'])
@login_required
def generate_validation_report():
    """Generate a new validation report"""
    try:
        # Reuse the logic from create_bulk_validation but format for this endpoint
        from models import Policy
        
        violations_found = 0
        validation_results = []
        
        # Validate all policies
        policies = Policy.query.all()
        for policy in policies:
            # Basic validation checks
            if policy.min_shift_length >= policy.max_shift_length:
                violations_found += 1
                validation_results.append(f"Policy {policy.policy_id}: Min shift length >= Max shift length")
            
            if policy.min_shift_length < 30:  # Less than 30 minutes
                violations_found += 1
                validation_results.append(f"Policy {policy.policy_id}: Min shift length too short")
            
            if policy.max_shift_length > 480:  # More than 8 hours
                violations_found += 1
                validation_results.append(f"Policy {policy.policy_id}: Max shift length too long")
        
        # Generate PDF
        pdf_buffer = generate_validation_pdf(validation_results, violations_found)
        
        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=f'validation_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf',
            mimetype='application/pdf'
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@constraints_bp.route('/detect-violations/<int:term_id>', methods=['POST'])
@login_required
def detect_violations(term_id):
    """Detect violations for a specific term"""
    try:
        # For now, perform the same policy checks
        # In a real implementation, this would check schedule assignments against policies for the term
        from models import Policy
        
        violations_found = 0
        
        # Validate all policies
        policies = Policy.query.all()
        for policy in policies:
            if policy.min_shift_length >= policy.max_shift_length:
                violations_found += 1
            if policy.min_shift_length < 30:
                violations_found += 1
            if policy.max_shift_length > 480:
                violations_found += 1
        
        return jsonify({
            'success': True,
            'violations_detected': violations_found,
            'message': f'Detection complete! Found {violations_found} violations.'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@constraints_bp.route('/api/configurations', methods=['PUT'])
@login_required
def update_constraints_configuration():
    """Update constraints configuration"""
    try:
        data = get_request_data()
        
        # Check if there's already a policy for any term (use first term if none specified)
        # Use latest existing policy (by id) if any, or create new one
        existing_policy = Policy.query.order_by(Policy.policy_id.desc()).first()
        
        if existing_policy:
            # Update existing policy
            policy = existing_policy
        else:
            # Create a new policy - get first available term
            first_term = Term.query.first()
            if not first_term:
                return jsonify({'success': False, 'error': 'No terms available. Please create a term first.'})
            
            policy = Policy(
                term_id=first_term.term_id,
                updated_by=current_user.user_id
            )
            # Set default values
            policy.min_shift_length = 120  # 2 hours
            policy.max_shift_length = 240  # 4 hours
            policy.min_break_length = 15
            policy.undesireable_start = 600  # 06:00
            policy.undesireable_end = 2200  # 22:00
            db.session.add(policy)
        policy.min_shift_length = int(float(data.get('min_shift_duration', 2)) * 60)  # Convert to minutes
        policy.max_shift_length = int(float(data.get('max_shift_duration', 4)) * 60)  # Convert to minutes
        policy.min_break_length = int(data.get('break_time', 15))
        # Remove invalid attribute max_daily_hours (not in model) - ignored
        
        # Time restrictions
        # Initialize defaults if not set yet to avoid stale values
        if not policy.undesireable_start:
            policy.undesireable_start = 600  # default 06:00
        if not policy.undesireable_end:
            policy.undesireable_end = 2200  # default 22:00

        if data.get('block_early_morning'):
            # Earliest allowed start after block boundary (e.g. 07:00)
            policy.undesireable_start = 700
        if data.get('block_late_evening'):
            # Latest allowed end before block boundary (e.g. 22:00)
            policy.undesireable_end = 2200
        
        # Custom time restrictions
        if data.get('custom_start_time'):
            custom_start = data['custom_start_time'].replace(':', '')
            try:
                policy.undesireable_start = int(custom_start)
            except ValueError:
                pass
        if data.get('custom_end_time'):
            custom_end = data['custom_end_time'].replace(':', '')
            try:
                policy.undesireable_end = int(custom_end)
            except ValueError:
                pass
        
        # Weekend and holiday restrictions
        if data.get('block_weekends'):
            policy.undesirable_windows = policy.undesirable_windows or {}
            policy.undesirable_windows['weekends_blocked'] = True
        
        if data.get('block_holidays'):
            policy.undesirable_windows = policy.undesirable_windows or {}
            policy.undesirable_windows['holidays_blocked'] = True
        
        # Student preferences settings
        policy.volunteer_preferences = {
            'respect_preferences': data.get('respect_preferences', True),
            'fair_distribution': data.get('fair_distribution', True),
            'early_volunteers': data.get('early_volunteers', []),
            'late_volunteers': data.get('late_volunteers', []),
            'weekend_volunteers': data.get('weekend_volunteers', [])
        }
        
        # Clear existing preferences for this policy and add new ones
        existing_preferences = policy.volunteer_preferences.get('preferences', [])
        
        # Save volunteer preferences
        volunteer_types = [
            ('early_volunteers', 'early_morning'),
            ('late_volunteers', 'late_evening'), 
            ('weekend_volunteers', 'weekend')
        ]
        
        # Remove old preferences of these types
        updated_preferences = [p for p in existing_preferences 
                             if p.get('preference_type') not in ['early_morning', 'late_evening', 'weekend']]
        
        # Add new preferences
        for volunteer_key, preference_type in volunteer_types:
            user_ids = data.get(volunteer_key, [])
            for user_id in user_ids:
                if user_id:  # Skip empty values
                    preference_data = {
                        'preference_id': len(updated_preferences) + 1,
                        'user_id': int(user_id),
                        'preference_type': preference_type,
                        'is_volunteer': True,
                        'created_by': current_user.user_id,
                        'created_at': datetime.now().isoformat(),
                        'notes': ''
                    }
                    updated_preferences.append(preference_data)
        
        policy.volunteer_preferences['preferences'] = updated_preferences
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(policy, 'volunteer_preferences')
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Constraints configuration saved successfully',
            'policy_id': policy.policy_id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@constraints_bp.route('/api/schedules', methods=['POST'])
@login_required
def create_constrained_schedule():
    """Create a new schedule using constraints from the setup wizard"""
    try:
        data = get_request_data()
        
        # Validate required fields
        required_fields = ['term_id', 'start_date', 'end_date']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }), 400
        
        term_id = data['term_id']
        start_date = data['start_date']
        end_date = data['end_date']
        preview_mode = data.get('preview_mode', True)
        
        # Create or update policy with the constraints
        policy = Policy.query.filter_by(term_id=term_id).first()
        if not policy:
            policy = Policy(
                term_id=term_id,
                updated_by=current_user.user_id,
                **Policy.get_default_values()
            )
            db.session.add(policy)
        
        # Update policy with wizard settings
        policy.min_shift_length = int(float(data.get('min_shift_duration', 2)) * 60)  # Convert to minutes
        policy.max_shift_length = int(float(data.get('max_shift_duration', 4)) * 60)  # Convert to minutes
        policy.min_break_length = int(data.get('break_time', 15))
        policy.max_daily_hours = int(data.get('max_daily_hours', 8))
        
        # Time restrictions
        if data.get('block_early_morning'):
            policy.undesireable_start = 700  # 7:00 AM
        if data.get('block_late_evening'):
            policy.undesireable_end = 2200   # 10:00 PM
        
        # Custom time restrictions
        if data.get('custom_start_time'):
            custom_start = data['custom_start_time'].replace(':', '')
            policy.undesireable_start = int(custom_start)
        if data.get('custom_end_time'):
            custom_end = data['custom_end_time'].replace(':', '')
            policy.undesireable_end = int(custom_end)
        
        # Clear existing preferences for this policy and add new ones from the wizard
        early_volunteers = data.get('early_volunteers', [])
        late_volunteers = data.get('late_volunteers', [])
        weekend_volunteers = data.get('weekend_volunteers', [])
        
        if not policy.volunteer_preferences:
            policy.volunteer_preferences = {'preferences': []}
        
        # Clear existing preferences
        policy.volunteer_preferences['preferences'] = []
        
        # Add new volunteer preferences to policy JSON
        all_volunteers = set()
        
        for user_id in early_volunteers:
            if user_id and user_id not in all_volunteers:
                policy.volunteer_preferences['preferences'].append({
                    'preference_id': len(policy.volunteer_preferences['preferences']) + 1,
                    'user_id': int(user_id),
                    'preference_type': 'early_morning',
                    'is_volunteer': True,
                    'created_by': current_user.user_id,
                    'created_at': datetime.now().isoformat(),
                    'notes': ''
                })
                all_volunteers.add(user_id)
        
        for user_id in late_volunteers:
            if user_id and user_id not in all_volunteers:
                policy.volunteer_preferences['preferences'].append({
                    'preference_id': len(policy.volunteer_preferences['preferences']) + 1,
                    'user_id': int(user_id),
                    'preference_type': 'late_evening',
                    'is_volunteer': True,
                    'created_by': current_user.user_id,
                    'created_at': datetime.now().isoformat(),
                    'notes': ''
                })
                all_volunteers.add(user_id)
        
        for user_id in weekend_volunteers:
            if user_id and user_id not in all_volunteers:
                policy.volunteer_preferences['preferences'].append({
                    'preference_id': len(policy.volunteer_preferences['preferences']) + 1,
                    'user_id': int(user_id),
                    'preference_type': 'weekend',
                    'is_volunteer': True,
                    'created_by': current_user.user_id,
                    'created_at': datetime.now().isoformat(),
                    'notes': ''
                })
                all_volunteers.add(user_id)
        
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(policy, 'volunteer_preferences')
        policy.updated_by = current_user.user_id
        db.session.commit()
        
        # Generate schedule (simplified for now)
        if preview_mode:
            message = "Schedule preview generated successfully! Review the constraints and settings."
            redirect_url = url_for('constraints.validation_reports')
        else:
            message = "Schedule generated successfully!"
            redirect_url = url_for('scheduler.index')
        
        return jsonify({
            'success': True,
            'message': message,
            'redirect_url': redirect_url
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# Policy Management API Routes

# This endpoint is redundant - use GET /api/policies instead
# @constraints_bp.route('/api/policies/list')
# def list_policies_api():
#     """List all policies with details"""
#     try:
#         from models import Policy, Term
#         
#         policies = db.session.query(Policy, Term).join(Term, Policy.term_id == Term.term_id, isouter=True).all()
#         
#         policies_data = []
#         for policy, term in policies:
#             policies_data.append({
#                 'policy_id': policy.policy_id,
#                 'term_name': term.name if term else f'Term {policy.term_id}',
#                 'term_id': policy.term_id,
#                 'min_shift_length': policy.min_shift_length,
#                 'max_shift_length': policy.max_shift_length,
#                 'min_break_length': policy.min_break_length,
#                 'max_break_length': policy.max_break_length,
#                 'undesireable_start': policy.undesireable_start,
#                 'undesireable_end': policy.undesireable_end,
#                 'updated_by': policy.updated_by,
#                 'created_at': 'N/A',  # Policy model doesn't have created_at
#                 'updated_at': 'Recently'  # Policy model doesn't have updated_at
#             })
#         
#         return jsonify({
#             'success': True,
#             'policies': policies_data
#         })
#     except Exception as e:
#         return jsonify({'success': False, 'error': str(e)})

@constraints_bp.route('/api/policies', methods=['POST'])
@login_required
def create_policy_api():
    """Create a new policy via API"""
    try:
        data = get_request_data()
        
        # Validate required fields
        required_fields = ['term_id', 'min_shift_length', 'max_shift_length']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400
        
        # Validate policy data
        validation_result = validate_policy_data(data)
        if not validation_result['valid']:
            return jsonify({'success': False, 'error': validation_result['error']}), 400
        
        # Check if policy already exists for this term - if so, update it instead
        existing_policy = Policy.query.filter_by(term_id=data['term_id']).first()
        if existing_policy:
            # Update existing policy
            existing_policy.min_shift_length = int(data['min_shift_length'])
            existing_policy.max_shift_length = int(data['max_shift_length'])
            existing_policy.min_break_length = int(data.get('min_break_length', 15))
            existing_policy.max_break_length = int(data.get('max_break_length', 60))
            existing_policy.undesireable_start = int(data.get('undesireable_start', 600))
            existing_policy.undesireable_end = int(data.get('undesireable_end', 2200))
            existing_policy.updated_by = current_user.user_id
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Policy updated successfully',
                'policy_id': existing_policy.policy_id
            })
        
        # Create new policy
        policy = Policy(
            term_id=data['term_id'],
            min_shift_length=int(data['min_shift_length']),
            max_shift_length=int(data['max_shift_length']),
            min_break_length=int(data.get('min_break_length', 15)),
            max_break_length=int(data.get('max_break_length', 60)),
            undesireable_start=int(data.get('undesireable_start', 600)),  # 6:00 AM
            undesireable_end=int(data.get('undesireable_end', 2200)),     # 10:00 PM
            updated_by=current_user.user_id
        )
        
        db.session.add(policy)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Policy created successfully',
            'policy_id': policy.policy_id
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@constraints_bp.route('/api/policies/<int:policy_id>', methods=['PUT'])
@login_required
def update_policy_api(policy_id):
    """Update an existing policy via API"""
    try:
        policy = db.session.get(Policy, policy_id)
        if not policy:
            abort(404)
        data = get_request_data()
        
        # Update fields if provided
        if 'min_shift_length' in data:
            policy.min_shift_length = int(data['min_shift_length'])
        if 'max_shift_length' in data:
            policy.max_shift_length = int(data['max_shift_length'])
        if 'min_break_length' in data:
            policy.min_break_length = int(data['min_break_length'])
        if 'max_break_length' in data:
            policy.max_break_length = int(data['max_break_length'])
        if 'undesireable_start' in data:
            policy.undesireable_start = int(data['undesireable_start'])
        if 'undesireable_end' in data:
            policy.undesireable_end = int(data['undesireable_end'])
        
        # Validate the updated policy state
        validation_data = {
            'term_id': policy.term_id,
            'min_shift_length': policy.min_shift_length,
            'max_shift_length': policy.max_shift_length,
            'min_break_length': policy.min_break_length,
            'max_break_length': policy.max_break_length,
            'undesireable_start': policy.undesireable_start,
            'undesireable_end': policy.undesireable_end
        }
        
        validation_result = validate_policy_data(validation_data)
        if not validation_result['valid']:
            db.session.rollback()
            return jsonify({'success': False, 'error': validation_result['error']}), 400

        policy.updated_by = current_user.user_id
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Policy updated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# Policy Management Interface

@constraints_bp.route('/policies')
@login_required
def policies():
    """Render policy management page."""
    return render_template('policy_management.html')

@constraints_bp.route('/validation-reports')
@login_required
def validation_reports():
    """Validation reports dashboard"""
    # Redirect to validation dashboard for now
    return redirect(url_for('constraints.validation_dashboard'))

@constraints_bp.route('/policies')
@login_required
def policy_management():
    """Policy management interface"""
    return render_template('policy_management.html')

@constraints_bp.route('/api/terms', methods=['GET'])
@login_required
def get_terms_api():
    """Get all available terms"""
    try:
        terms = Term.query.all()
        terms_data = [{
            'term_id': term.term_id,
            'name': term.name
        } for term in terms]
        
        return jsonify({
            'success': True,
            'terms': terms_data
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# Student Management Routes
@constraints_bp.route('/students')
@login_required
def student_management():
    """Student management dashboard"""
    if current_user.role == 'student':
        flash('Access denied. Supervisor privileges required.', 'error')
        return redirect(url_for('auth.shiftManagement'))
    
    return render_template('student_management.html')

@constraints_bp.route('/api/students', methods=['GET'])
@login_required
def list_students_api():
    """API to list all students"""
    if current_user.role == 'student':
        return {'success': False, 'error': 'Access denied'}, 403
    
    try:
        students = User.query.filter_by(role='student', is_active=True).all()
        students_data = []
        
        for student in students:
            student_data = {
                'user_id': student.user_id,
                'name': student.name,
                'email': student.email,
                'is_active': student.is_active,
                'calendar_token': student.calendar_token,
                'total_shifts': len(student.shifts) if student.shifts else 0,
                'total_hours': sum([shift.duration_minutes / 60 for shift in student.shifts]) if student.shifts else 0
            }
            students_data.append(student_data)
        
        return {
            'success': True,
            'students': students_data,
            'total': len(students_data)
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}, 500

@constraints_bp.route('/api/students', methods=['POST'])
@login_required
def create_student_api():
    """API to create a new student"""
    if current_user.role == 'student':
        return {'success': False, 'error': 'Access denied'}, 403
    
    try:
        data = request.get_json()
        
        # Validation
        required_fields = ['name', 'email', 'password']
        for field in required_fields:
            if not data.get(field):
                return {'success': False, 'error': f'Field {field} is required'}, 400
        
        # Check if email already exists
        existing_user = User.query.filter_by(email=data['email']).first()
        if existing_user:
            return {'success': False, 'error': 'Email already exists'}, 400
        
        # Create new student
        student = User(
            name=data['name'],
            email=data['email'],
            role='student',
            is_active=True
        )
        student.set_password(data['password'])
        
        # Generate calendar token
        import uuid
        student.calendar_token = str(uuid.uuid4())
        
        db.session.add(student)
        db.session.commit()

        # New student affects Outputs index stats; invalidate summary cache.
        cache.delete(outputs_index_key())

        return {
            'success': True,
            'message': 'Student created successfully',
            'student': {
                'user_id': student.user_id,
                'name': student.name,
                'email': student.email,
                'calendar_token': student.calendar_token
            }
        }
    except Exception as e:
        db.session.rollback()
        return {'success': False, 'error': str(e)}, 500

@constraints_bp.route('/api/students/<int:student_id>', methods=['PUT'])
@login_required
def update_student_api(student_id):
    """API to update a student"""
    if current_user.role == 'student':
        return {'success': False, 'error': 'Access denied'}, 403
    
    try:
        student = db.session.get(User, student_id)
        if not student or student.role != 'student':
            return {'success': False, 'error': 'Student not found'}, 404
        
        data = request.get_json()
        
        # Update fields
        if 'name' in data:
            student.name = data['name']
        if 'email' in data:
            # Check if new email already exists
            existing = User.query.filter_by(email=data['email']).first()
            if existing and existing.user_id != student.user_id:
                return {'success': False, 'error': 'Email already exists'}, 400
            student.email = data['email']
        if 'password' in data and data['password']:
            student.set_password(data['password'])
        if 'is_active' in data:
            student.is_active = data['is_active']
        
        db.session.commit()

        # If activation status changed, Outputs index student count may change.
        if 'is_active' in data:
            cache.delete(outputs_index_key())
        
        return {
            'success': True,
            'message': 'Student updated successfully',
            'student': {
                'user_id': student.user_id,
                'name': student.name,
                'email': student.email,
                'is_active': student.is_active
            }
        }
    except Exception as e:
        db.session.rollback()
        return {'success': False, 'error': str(e)}, 500

@constraints_bp.route('/api/students/<int:student_id>', methods=['DELETE'])
@login_required
def delete_student_api(student_id):
    """API to deactivate/delete a student"""
    if current_user.role == 'student':
        return {'success': False, 'error': 'Access denied'}, 403
    
    try:
        student = db.session.get(User, student_id)
        if not student or student.role != 'student':
            return {'success': False, 'error': 'Student not found'}, 404
        
        # Instead of deleting, deactivate the student to preserve shift history
        student.is_active = False
        db.session.commit()

        # Deactivation affects student counts on Outputs index.
        cache.delete(outputs_index_key())

        return {
            'success': True,
            'message': 'Student deactivated successfully'
        }
    except Exception as e:
        db.session.rollback()
        return {'success': False, 'error': str(e)}, 500

