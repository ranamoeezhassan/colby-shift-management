from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from . import availability_bp
from models import db, User, Availability, Term
import requests
import csv
import io
from dotenv import load_dotenv
from datetime import datetime

# GitHub Issues #1-12: Availability & Inputs
# Features: Availability management, CSV import, templates, deadlines, etc.

@availability_bp.route('/', methods=['GET', 'POST'])
def availability():
    # Term selection similar to staffing: query param term_id selects active term, else latest
    selected_term_id = request.args.get('term_id', type=int)
    available_terms = Term.query.order_by(Term.start_date.desc()).all()
    if selected_term_id:
        active_term = Term.query.get(selected_term_id)
    else:
        active_term = available_terms[0] if available_terms else None
    if not active_term:
        # No term exists yet; instruct user to create one on staffing page
        return redirect(url_for('staffing.index'))

    if request.method == 'POST':
        action = request.form.get('action')

        # -------------------
        # CSV UPLOAD
        # -------------------
        if action == 'upload':
            file = request.files.get('csv_file')
            if not file or not file.filename.endswith('.csv'):
                flash('Please upload a valid CSV file.', 'error')
                return redirect(url_for('availability.availability', term_id=active_term.term_id))

            try:
                stream = io.StringIO(file.stream.read().decode('UTF8'))
                reader = csv.DictReader(stream)

                for row in reader:
                    user = User.query.filter_by(name=row['name']).first()
                    if not user:
                        continue

                    # Normalize day names to 3-letter format
                    day = row['day_of_week'].strip().capitalize()[:3]

                    start_time = datetime.strptime(row['start_time'], '%H:%M').time()
                    end_time = datetime.strptime(row['end_time'], '%H:%M').time()

                    new_avail = Availability(
                        user_id=user.user_id,
                        term_id=active_term.term_id,
                        day_of_week=day,
                        start_time=start_time,
                        end_time=end_time
                    )
                    db.session.add(new_avail)

                db.session.commit()
                flash('CSV data uploaded successfully!', 'success')

            except Exception as e:
                db.session.rollback()
                flash(f'Error uploading CSV: {e}', 'error')

            return redirect(url_for('availability.availability', term_id=active_term.term_id))

        # -------------------
        # MANUAL UPDATES (24-hour format)
        # -------------------
        elif action == 'update':
            try:
                student_names = request.form.getlist('student_name[]')
                days = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']

                # Get all day columns once
                day_blocks = {day: request.form.getlist(f'{day}[]') for day in days}

                # 1) Aggregate non-empty raw blocks by (student_name, day_key)
                #    Example: aggregated[('Alice', 'Mon')] = ['09:00-12:00', '13:00-17:00']
                aggregated = {}

                for row_index, raw_name in enumerate(student_names):
                    name = (raw_name or "").strip()
                    if not name:
                        continue

                    for day in days:
                        blocks_list = day_blocks.get(day, [])
                        cell_value = (
                            blocks_list[row_index].strip()
                            if row_index < len(blocks_list) and blocks_list[row_index] is not None
                            else ''
                        )

                        if not cell_value:
                            continue  # this row doesn't change this (user, day)

                        day_key = day.capitalize()[:3]  # 'mon' -> 'Mon', etc.

                        # Allow multiple blocks separated by commas, e.g. "09:00-12:00, 13:00-17:00"
                        for segment in cell_value.split(','):
                            seg = segment.strip()
                            if not seg:
                                continue
                            aggregated.setdefault((name, day_key), []).append(seg)

                any_error = False

                # 2) For each (user, day), parse all blocks; then replace DB rows for that (user, day)
                for (student_name, day_key), blocks in aggregated.items():
                    user = User.query.filter_by(name=student_name).first()
                    if not user:
                        continue

                    parsed_blocks = []

                    for raw_block in blocks:
                        # Normalize block: replace unicode dashes with normal hyphen
                        block = raw_block.replace('–', '-').strip()

                        # Must contain exactly one '-' separating start and end
                        if '-' not in block:
                            any_error = True
                            flash(
                                f"Invalid block '{raw_block}' for {student_name} on {day_key}. "
                                "Use HH:MM-HH:MM, e.g. 09:00-12:00.",
                                'error'
                            )
                            continue

                        try:
                            start_str, end_str = [t.strip() for t in block.split('-', 1)]

                            # STRICT 24-hour format only
                            start_time = datetime.strptime(start_str, '%H:%M').time()
                            end_time = datetime.strptime(end_str, '%H:%M').time()

                            parsed_blocks.append((start_time, end_time))

                        except ValueError:
                            any_error = True
                            flash(
                                f"Invalid time format in block '{raw_block}' for {student_name} on {day_key}. "
                                "Use 24-hour format like 09:00-17:00 (multiple: 09:00-12:00, 13:00-17:00).",
                                'error'
                            )

                    # If at least one block parsed correctly, replace that user/day in the DB
                    if parsed_blocks:
                        Availability.query.filter_by(
                            user_id=user.user_id,
                            term_id=active_term.term_id,
                            day_of_week=day_key
                        ).delete()

                        for start_time, end_time in parsed_blocks:
                            new_avail = Availability(
                                user_id=user.user_id,
                                term_id=active_term.term_id,
                                day_of_week=day_key,
                                start_time=start_time,
                                end_time=end_time
                            )
                            db.session.add(new_avail)

                db.session.commit()

                if any_error:
                    flash('Availability updated (some blocks had errors). Check messages above.', 'error')
                else:
                    flash('Availability updated successfully!', 'success')

            except Exception as e:
                db.session.rollback()
                flash(f'Error updating availability: {e}', 'error')

        # Redirect to preserve PRG pattern
        return redirect(url_for('availability.availability', term_id=active_term.term_id))

    # -------------------
    # GET REQUEST — SHOW CURRENT AVAILABILITY
    # -------------------
    if current_user.role.lower() == 'supervisor':
        all_availability = Availability.query.join(User).filter(
            Availability.term_id == active_term.term_id
        ).all()
    else:
        all_availability = Availability.query.filter_by(
            user_id=current_user.user_id,
            term_id=active_term.term_id
        ).all()

    # Organize data by user → day (3-letter format)
    availability_data = {}
    for a in all_availability:
        user = a.user
        if user.name not in availability_data:
            availability_data[user.name] = {d: "" for d in ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']}

        day_key = a.day_of_week[:3].capitalize()
        start_str = a.start_time.strftime("%H:%M")
        end_str = a.end_time.strftime("%H:%M")
        new_block = f"{start_str}-{end_str}"

        if not a.start_time or not a.end_time:
            continue

        existing = availability_data[user.name].get(day_key, "")
        if existing:
            # Append another block for that day, comma-separated
            availability_data[user.name][day_key] = existing + ", " + new_block
        else:
            availability_data[user.name][day_key] = new_block
    

    return render_template(
        'availability_index.html',
        availability_data=availability_data,
        active_term=active_term,
        available_terms=available_terms
    )