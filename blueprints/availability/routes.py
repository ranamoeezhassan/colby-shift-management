from flask import Blueprint, request, jsonify, current_app, send_from_directory, Response, render_template
from blueprints.availability import availability_bp
from flask_login import current_user, login_required
from models import db, User, Availability, Term
from datetime import datetime
import csv
import io




@availability_bp.route('/page', methods=['GET'])
@login_required
def availability_page():
    return render_template('availability_index.html')


# --------- REST API: get terms ---------
@availability_bp.route('/api/v1/terms', methods=['GET'])
@login_required
def get_terms():
    terms = Term.query.order_by(Term.start_date.desc()).all()
    data = [
        {
            "term_id": t.term_id,
            "name": t.name,
            "start_date": t.start_date.isoformat(),
            "end_date": t.end_date.isoformat()
        }
        for t in terms
    ]
    return jsonify(data), 200


# --------- REST API: get availability for a term ---------
@availability_bp.route('/api/v1/availability', methods=['GET'])
@login_required
def get_availability():
    term_id = request.args.get('term_id', type=int)
    if not term_id:
        return jsonify({"error": "term_id is required"}), 400

    term = db.session.get(Term, term_id)
    if not term:
        return jsonify({"error": "Term not found"}), 404

    if current_user.role.lower() == 'supervisor':
        all_availability = Availability.query.join(User).filter(
            Availability.term_id == term_id
        ).all()
    else:
        all_availability = Availability.query.filter_by(
            user_id=current_user.user_id,
            term_id=term_id
        ).all()

    # Build structure
    result = {}
    for a in all_availability:
        name = a.user.name
        if name not in result:
            result[name] = {d: [] for d in ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']}

        day_key = a.day_of_week[:3].capitalize()
        start_str = a.start_time.strftime("%H:%M")
        end_str = a.end_time.strftime("%H:%M")
        block = f"{start_str}-{end_str}"
        result[name][day_key].append(block)

    return jsonify({
        "term_id": term_id,
        "availability": result
    }), 200


# --------- REST API: update availability (JSON) ---------
@availability_bp.route('/api/v1/availability', methods=['POST'])
@login_required
def update_availability():
    data = request.get_json(silent=True) or {}
    term_id = data.get("term_id")
    rows = data.get("rows", [])

    if not term_id:
        return jsonify({"error": "term_id is required"}), 400

    term = db.session.get(Term, term_id)
    if not term:
        return jsonify({"error": "Term not found"}), 404

    days_keys = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    any_error = False
    errors = []

    
    aggregated = {}

    for row in rows:
        name = (row.get("student_name") or "").strip()
        if not name:
            continue

        user = User.query.filter_by(name=name).first()
        if not user:
            any_error = True
            errors.append(f"User '{name}' not found")
            continue

        for day_key in days_keys:
            cell_value = (row.get(day_key) or "").strip()
            if not cell_value:
                Availability.query.filter_by(
                user_id=user.user_id,
                term_id=term.term_id,
                day_of_week=day_key,
                ).delete()
                continue

            # multiple blocks: "09:00-12:00, 13:00-17:00"
            for segment in cell_value.split(','):
                seg = segment.replace('–', '-').strip()
                if not seg:
                    continue
                aggregated.setdefault((user.user_id, day_key), []).append(seg)

    #Write to DB
    for (user_id, day_key), blocks in aggregated.items():
        parsed_blocks = []

        for raw_block in blocks:
            block = raw_block.replace('–', '-').strip()
            if '-' not in block:
                any_error = True
                errors.append(
                    f"Invalid block '{raw_block}' for user_id {user_id} on {day_key}."
                )
                continue

            try:
                start_str, end_str = [t.strip() for t in block.split('-', 1)]
                start_time = datetime.strptime(start_str, '%H:%M').time()
                end_time = datetime.strptime(end_str, '%H:%M').time()
                parsed_blocks.append((start_time, end_time))
            except ValueError:
                any_error = True
                errors.append(
                    f"Invalid time format in block '{raw_block}' for user_id {user_id} on {day_key}. "
                    "Use HH:MM-HH:MM (e.g. 09:00-17:00)."
                )

        if parsed_blocks:
            # Overwrite that user/day/term
            Availability.query.filter_by(
                user_id=user_id,
                term_id=term_id,
                day_of_week=day_key
            ).delete()

            for start_time, end_time in parsed_blocks:
                db.session.add(Availability(
                    user_id=user_id,
                    term_id=term_id,
                    day_of_week=day_key,
                    start_time=start_time,
                    end_time=end_time
                ))

    db.session.commit()

    status = 207 if any_error else 200
    return jsonify({
        "message": "Availability updated",
        "errors": errors
    }), status


# --------- REST API: CSV upload (overwrite per user/day) ---------
@availability_bp.route('/api/v1/availability/upload', methods=['POST'])
@login_required
def upload_availability_csv():
    term_id = request.form.get('term_id', type=int)
    if not term_id:
        return jsonify({"error": "term_id is required"}), 400

    term = db.session.get(Term, term_id)
    if not term:
        return jsonify({"error": "Term not found"}), 404

    file = request.files.get('csv_file')
    if not file or not file.filename.endswith('.csv'):
        return jsonify({"error": "Please upload a valid CSV file"}), 400

    try:
        stream = io.StringIO(file.stream.read().decode('UTF8'))
        reader = csv.DictReader(stream)

        aggregated = {}
        errors = []
        any_error = False
        total_rows = 0
        success_rows = 0
        error_rows = 0

        for row in reader:
            name = (row.get('name') or '').strip()
            day_raw = (row.get('day_of_week') or '').strip()
            start_raw = (row.get('start_time') or '').strip()
            end_raw = (row.get('end_time') or '').strip()

            # Skip completely empty rows (e.g. trailing blank line)
            if not (name or day_raw or start_raw or end_raw):
                continue

            total_rows += 1

            if not name or not day_raw or not start_raw or not end_raw:
                any_error = True
                error_rows += 1
                errors.append(f"Row {total_rows}: missing required fields.")
                continue

            user = User.query.filter_by(name=name).first()
            if not user:
                any_error = True
                error_rows += 1
                errors.append(
                    f"Row {total_rows}: user '{name}' not found. "
                    "Check spelling or create this user first."
                )
                continue

            day_key = day_raw.capitalize()[:3]

            try:
                start_time = datetime.strptime(start_raw, '%H:%M').time()
                end_time = datetime.strptime(end_raw, '%H:%M').time()
            except ValueError:
                any_error = True
                error_rows += 1
                errors.append(
                    f"Row {total_rows}: invalid time for {name} on {day_raw}: "
                    f"'{start_raw}-{end_raw}'. Expected HH:MM (e.g. 09:00)."
                )
                continue

            # If we got here, this row is valid
            success_rows += 1
            aggregated.setdefault((user.user_id, day_key), []).append((start_time, end_time))

        # Overwrite per (user, day)
        for (user_id, day_key), blocks in aggregated.items():
            Availability.query.filter_by(
                user_id=user_id,
                term_id=term_id,
                day_of_week=day_key
            ).delete()

            for start_time, end_time in blocks:
                db.session.add(Availability(
                    user_id=user_id,
                    term_id=term_id,
                    day_of_week=day_key,
                    start_time=start_time,
                    end_time=end_time
                ))

        db.session.commit()

        # Decide status + top-level message
        if success_rows == 0:
            # Nothing imported – treat as real failure
            status = 400
            message = "CSV processed but no rows were imported. Please fix the errors and try again."
        elif any_error:
            # Partial success
            status = 207  # Multi-Status
            message = (
                f"CSV processed with some issues: {success_rows}/{total_rows} "
                "rows were imported."
            )
        else:
            # All good
            status = 200
            message = f"CSV processed successfully: {success_rows}/{total_rows} rows imported."

        return jsonify({
            "message": message,
            "errors": errors,
            "summary": {
                "total_rows": total_rows,
                "processed_rows": success_rows,
                "error_rows": error_rows,
                "partial_success": any_error and success_rows > 0
            }
        }), status

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error uploading CSV: {e}"}), 500

# --------- Export Availability into CSV ---------
@availability_bp.route('/api/v1/availability/export', methods=['GET'])
@login_required
def export_availability_csv():
    term_id = request.args.get('term_id', type=int)
    if not term_id:
        return jsonify({"error": "term_id is required"}), 400

    term = db.session.get(Term, term_id)
    if not term:
        return jsonify({"error": "Term not found"}), 404

    
    if current_user.role.lower() == 'supervisor':
        all_availability = Availability.query.join(User).filter(
            Availability.term_id == term_id
        ).all()
    else:
        all_availability = Availability.query.filter_by(
            user_id=current_user.user_id,
            term_id=term_id
        ).all()

    # Map 3-letter day keys back to full names for CSV
    day_full_map = {
        'Mon': 'Monday',
        'Tue': 'Tuesday',
        'Wed': 'Wednesday',
        'Thu': 'Thursday',
        'Fri': 'Friday',
        'Sat': 'Saturday',
        'Sun': 'Sunday',
    }

    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    writer.writerow(['name', 'day_of_week', 'start_time', 'end_time'])

    for a in all_availability:
        name = a.user.name
        day_key = a.day_of_week[:3].capitalize()
        day_full = day_full_map.get(day_key, a.day_of_week)
        start_str = a.start_time.strftime("%H:%M")
        end_str = a.end_time.strftime("%H:%M")
        writer.writerow([name, day_full, start_str, end_str])

    csv_data = output.getvalue()
    output.close()

    filename = f"availability_term_{term_id}.csv"
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


# --------- REST API: clear one student's availability for this term ---------
@availability_bp.route('/api/v1/availability/clear-row', methods=['POST'])
@login_required
def clear_row():
    data = request.get_json(silent=True) or {}
    term_id = data.get("term_id")
    student_name = (data.get("student_name") or "").strip()

    if not term_id or not student_name:
        return jsonify({"error": "term_id and student_name are required"}), 400

    user = User.query.filter_by(name=student_name).first()
    if not user:
        return jsonify({"error": f"User '{student_name}' not found"}), 404

    Availability.query.filter_by(
        user_id=user.user_id,
        term_id=term_id
    ).delete()
    db.session.commit()

    return jsonify({"message": f"Cleared availability for {student_name} in term {term_id}"}), 200

@availability_bp.route('/api/v1/availability/clear-all', methods=['POST'])
@login_required
def clear_all_availability():
    data = request.get_json(silent=True) or {}
    term_id = data.get("term_id")

    if not term_id:
        return jsonify({"error": "term_id is required"}), 400

    term = db.session.get(Term, term_id)
    if not term:
        return jsonify({"error": "Term not found"}), 404

    # Delete all availability rows for this term
    deleted_count = Availability.query.filter_by(term_id=term_id).delete(synchronize_session=False)
    db.session.commit()

    return jsonify({
        "message": f"Cleared {deleted_count} availability entries for term '{term.name}'.",
        "deleted": deleted_count,
        "term_id": term_id
    }), 200