# Colby Shift Management

A Flask-based staffing and scheduling application for managing student availability, staffing coverage needs, validation rules, and generated schedules across academic terms.

The app supports a supervisor workflow and a student workflow:

- Supervisors define terms, staffing requirements, policies, and constraints.
- Students submit weekly availability and can view their assigned schedule.
- The scheduler generates shift assignments that respect staffing needs and policy limits.
- Outputs can be previewed, exported to CSV/iCalendar, and shared as public student calendar links.
- Optional AI assistance helps users navigate the app and understand pages.

---

## What the project does

This system is built to manage the full cycle of shift staffing for a campus or operations team:

1. Create a term and define staffing coverage requirements by day and time.
2. Collect student availability for that term.
3. Apply constraints and policy rules such as min/max shift lengths, undesirable windows, gap handling, and transition times.
4. Generate a schedule automatically using the built-in scheduling logic.
5. Review generated shifts, adjust them manually when needed, and validate results.
6. Share outputs with staff or students via dashboards, exports, and calendar feeds.


---

## Core features

### Authentication and role management

- Flask login and user accounts with roles such as student and supervisor.
- Signup/login pages with optional Google OAuth and reCAPTCHA support.
- Role-based access to pages and actions.

### Term and staffing management

- Create academic or operational terms with start/end dates and availability deadlines.
- Add coverage needs by day of week, time block, required role, and headcount.
- Lock and unlock terms as needed.

### Availability collection

- Students submit availability in a weekly grid or CSV import/export workflow.
- Availability is stored per user, term, and day.
- Supervisors can review or upload availability data for all students.

### Constraint and policy validation

- Shift duration and time-window constraints.
- Undesirable time windows.
- Gap management to reduce fragmented or low-quality shifts.
- Transition-time enforcement between consecutive shifts.
- Volunteer preferences and validation dashboard logic.

### Scheduling engine

- Uses a Python scheduler class to generate daily schedules.
- Checks user availability, staffing needs, and gap/transition rules.
- Can overwrite previous generated shifts when requested.
- Produces schedule summaries and warnings for problematic assignments.

### Outputs and sharing

- Schedule previews and all-student views.
- CSV export for staffing records.
- iCalendar export for student or supervisor calendars.
- Public calendar URLs generated from secure calendar tokens.
- Per-student schedule views and weekly breakdowns.

### AI assistant support

- A Groq/OpenAI-compatible navigation assistant can answer navigation questions using route and page context.
- Intended to help users find the right page or understand app features quickly.

---

## How it works

The app follows a term-based scheduling flow:

1. A supervisor creates a term with date boundaries.
2. Staffing needs are added for each day and time block.
3. Students submit availability windows for that term.
4. Policy settings are enforced for shift length, timing, and fairness rules.
5. The scheduler builds a schedule by matching staffing requirements to available users.
6. Results are reviewed through generation summary pages and validation tools.
7. Outputs are exported or shared with employees/students.

The main application logic is split into Flask blueprints:

- auth: login, signup, role handling, and OAuth.
- availability: availability forms, CSV import/export, and retrieval APIs.
- staffing: term creation, staffing needs, validation and coverage logic.
- constraints: policy configuration, validation dashboards, and rule enforcement.
- scheduler: schedule generation, week overview, and manual edits.
- outputs: schedule previews, student views, CSV/iCal exports, and public links.
- ai: AI-guided navigation support.

---

## Technology stack

- Python 3
- Flask
- Flask-SQLAlchemy
- Flask-Login
- Authlib for Google OAuth
- SQLite by default for local development
- PostgreSQL/MySQL compatible when database URL is provided for production
- Jinja templates for the UI
- iCalendar and reportlab support for exports and reports
- OpenAI-compatible Groq client for AI assistance

---

## Project structure

```text
app.py                     # Flask app entry point and config
models.py                 # SQLAlchemy models and policy logic
schedule_generator.py      # Schedule generation and gap analysis
seed_data.py               # Demo data seeding script
cache.py                   # Cache utilities for outputs and scheduling data
requirements.txt           # Python runtime dependencies

blueprints/
  ai/
  auth/
  availability/
  constraints/
  outputs/
  scheduler/
  staffing/

utils/
  pdf_generator.py
  recaptcha.py

instance/
  shift_management.db      # SQLite database created locally

tests/
  ...                     # Pytest coverage for routes and data logic
```

---

## Environment variables

The app reads configuration from environment variables. A typical local setup includes:

```bash
SECRET_KEY=change-me
DATABASE_URL=optional-for-production
GOOGLE_CLIENT_ID=optional
GOOGLE_CLIENT_SECRET=optional
RECAPTCHA_SITE_KEY=optional
RECAPTCHA_SECRET_KEY=optional
GROQ_API_KEY=optional
GROQ_API_BASE_URL=https://api.groq.com/openai/v1
GROQ_MODEL=openai/gpt-oss-120b
DISABLE_RECAPTCHA=1  # optional for local/dev testing
PORT=5000
```

Notes:

- If no DATABASE_URL or JAWSDB_URL is set, the app uses a local SQLite database under the instance folder.
- If Google OAuth variables are not set, the app still runs normally but Google sign-in is skipped.
- If reCAPTCHA keys are absent, login/signup verification is skipped with a debug warning unless explicitly disabled.

---

## Setup and run locally

### 1. Clone and enter the project

```bash
git clone <repository-url>
cd colby-shift-management
```

### 2. Create a virtual environment

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

On macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a .env file in the project root if needed:

```bash
SECRET_KEY=dev-secret-key
DISABLE_RECAPTCHA=1
```

For production or real authentication features, add the additional optional variables described above.

### 5. Run the app

```bash
python app.py
```

The app starts on:

- http://127.0.0.1:5000

When running locally, Flask debug mode is enabled and a SQLite database is created automatically in the instance directory.

---

## Seed example data

The repository includes a seed script to build a realistic sample dataset with:

- a supervisor user
- student users
- a term
- policy settings
- staffing needs
- availability records
- sample assignments

Run it with:

```bash
python seed_data.py
```

This is useful for testing the dashboard, scheduling flow, and outputs without creating data manually.

---

## Typical workflow in the app

### Supervisor flow

1. Log in as a supervisor.
2. Create a term in the Staffing section.
3. Add coverage needs for each day/time block.
4. Review or upload availability from students.
5. Set or edit policies in the Constraints area.
6. Generate a schedule from the Scheduler page.
7. Review generation results and fix any issues.
8. Export CSV or iCalendar data from Outputs.

### Student flow

1. Sign up or log in.
2. Submit availability for the current term.
3. View schedule and public calendar links from the outputs pages.
4. Access assigned shift information and exported calendar feeds.

---

## Testing

The repository includes a pytest suite under the tests directory. To install the test dependencies and run the suite:

```bash
pip install -r tests/requirements-test.txt
pytest
```

You can also run a single test file:

```bash
pytest tests/test_auth_routes.py
pytest tests/test_outputs_routes.py
```

---

## Deployment notes

The app includes Heroku-oriented production settings:

- It checks DATABASE_URL or JAWSDB_URL for production database configuration.
- It supports a production port via the PORT environment variable.
- It adapts PostgreSQL and MySQL URLs for use with SQLAlchemy.

This makes it deployable to a service like Heroku, while local development remains SQLite-based.

---

## Additional notes

- The application intentionally separates features into blueprints to keep routes organized.
- Policy validation rules are stored in the database and may be updated over time as staffing needs evolve.
- Student calendar tokens are generated automatically and can be used to create public schedule links.
- The AI service is optional and only works when GROQ credentials are available.

---

## License

This project is licensed under the terms in the repository license file.
