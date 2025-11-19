from flask import jsonify, request, current_app, url_for
from flask_login import login_required, current_user
import os
import re

from . import ai_bp
from .groq_client import get_navigation_help


_PAGE_TEXT_CACHE: dict = {}


ROLE_PAGE_DESCRIPTIONS = {
    "student": {
        "dashboard": (
            "Student dashboard showing a summary of your schedule and any "
            "student-facing quick links (for example, a 'My Schedule' link)."
        ),
        "outputs_index": (
            "Outputs page for students. Focused on viewing your own schedule, "
            "downloading it, or copying a calendar/public link. Does not show "
            "management tools for other students."
        ),
        "student_schedule": (
            "Student schedule view showing your shifts in a weekly layout with "
            "dates, times, and locations. May include export or calendar options."
        ),
        "public_schedule": (
            "Public read-only schedule view for a single student that can be "
            "shared with others. Shows the same shifts as your own schedule."
        ),
    },
    "supervisor": {
        "dashboard": (
            "Supervisor dashboard landing page with a summary of constraints, "
            "violations, or quick links into Staffing, Availability, Scheduler, "
            "Constraints, and Outputs."
        ),
        "outputs_index": (
            "Outputs main page summarizing current term, total shifts, student "
            "count, and links to all student views, comparisons, previews, and exports."
        ),
        "student_schedule": (
            "Supervisor view of an individual student's schedule with weekly "
            "breakdowns and statistics such as hours and shift counts."
        ),
        "public_schedule": (
            "Public read-only schedule page for a student, accessible via secure token."
        ),
        "all_students_view": (
            "All Students view showing a list of students, their weekly shift counts "
            "and hours, with filters and search for balancing workloads."
        ),
        "scheduler_index": (
            "Scheduler main page with week-by-week overview, term selection, and "
            "controls for running the schedule generator."
        ),
        "staffing_index": (
            "Staffing page used to define academic terms and coverage requirements "
            "by day and time blocks."
        ),
        "constraints_index": (
            "Constraints page listing tools for policy configuration, gap management, "
            "duration validation, rejection rules, and validation reports."
        ),
        "availability_page": (
            "Availability grid where supervisors can view or upload student "
            "availability for the selected term."
        ),
        "outputs_preview": (
            "Preview page showing a full schedule by week, with constraint warnings "
            "and visual overlaps."
        ),
    },
}


def _load_page_text(relative_path: str) -> str:
    """
    Load a template/static page from disk and return a plain-text version
    with HTML tags stripped. This gives the model an accurate view of
    the actual UI labels without styling noise.
    """
    cache_key = relative_path
    if cache_key in _PAGE_TEXT_CACHE:
        return _PAGE_TEXT_CACHE[cache_key]

    root = current_app.root_path
    full_path = os.path.join(root, relative_path)

    try:
        with open(full_path, "r", encoding="utf-8") as f:
            html = f.read()
    except OSError:
        current_app.logger.warning("AI assistant: could not read page %s", full_path)
        _PAGE_TEXT_CACHE[cache_key] = ""
        return ""

    # Very simple HTML -> text: remove tags, collapse whitespace.
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Limit length to keep prompts reasonable.
    if len(text) > 1500:
        text = text[:1500] + " ..."

    _PAGE_TEXT_CACHE[cache_key] = text
    return text


def _build_routes_for_role(role: str) -> dict:
    """
    Build a dict of logical route names -> URLs that this role is allowed to see.

    We deliberately keep this conservative so the model never sees routes that
    shouldn't be visible for a given role.
    """
    role = (role or "").lower()

    routes = {
        "dashboard": url_for("auth.shiftManagement"),
        "outputs_index": url_for("outputs.index"),
    }

    if role == "student":
        # Students mostly need to see their own schedule.
        try:
            routes["student_schedule"] = url_for(
                "outputs.student_view", user_id=current_user.user_id
            )
        except Exception:
            # If the route cannot be built for some reason, just skip it.
            current_app.logger.exception("Failed to build student_schedule URL")

        # Students might also see a public calendar link if exposed elsewhere,
        # but we only reference it here if we can generate a URL safely.
        try:
            if getattr(current_user, "calendar_token", None):
                routes["public_schedule"] = url_for(
                    "outputs.public_schedule_view",
                    token=current_user.calendar_token,
                )
        except Exception:
            current_app.logger.exception("Failed to build public_schedule URL")

        return routes

    # Supervisors/admins: full toolset.
    try:
        routes.update(
            {
                "availability_page": url_for("availability.availability_page"),
                "staffing_index": url_for("staffing.index"),
                "constraints_index": url_for("constraints.index"),
                "scheduler_index": url_for("scheduler.index"),
                "outputs_preview": url_for("outputs.preview"),
                "all_students_view": url_for("outputs.all_students_view"),
            }
        )
    except Exception:
        # If any URL generation fails, log and continue with the rest.
        current_app.logger.exception("Failed to build one or more supervisor URLs")

    return routes


@ai_bp.route("/api/ai/query", methods=["POST"])
@login_required
def ai_query():
    """
    Single-shot navigation assistant endpoint.

    Expects JSON:
        {
            "question": "How do I ...?",
            "current_path": "/some/path"   # optional; falls back to request.path
        }
    """
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    current_path = data.get("current_path") or request.path

    if not question:
        return jsonify({"error": "Question is required."}), 400

    role = (getattr(current_user, "role", "") or "").lower()
    routes = _build_routes_for_role(role)

    # Map logical route names to actual template/static files so we can give
    # the model a plain-text snapshot of important pages.
    page_files = {
        # Shared / entry pages
        "dashboard": "blueprints/auth/templates/landing.html",

        # Outputs / student-focused views
        "outputs_index": "blueprints/outputs/templates/outputs_index.html",
        "student_schedule": "blueprints/outputs/templates/student_view.html",
        "public_schedule": "blueprints/outputs/templates/public_schedule_view.html",
        "all_students_view": "blueprints/outputs/templates/all_students.html",
        "outputs_preview": "blueprints/outputs/templates/preview.html",

        # Scheduler / staffing / constraints / availability (supervisors)
        "scheduler_index": "blueprints/scheduler/templates/scheduler_index.html",
        "staffing_index": "blueprints/staffing/templates/staffing_index.html",
        "constraints_index": "blueprints/constraints/templates/constraints_index.html",
        "availability_page": "blueprints/availability/static/availability_index.html",
    }

    pages = {}
    role_key = role or "supervisor"
    role_pages = ROLE_PAGE_DESCRIPTIONS.get(role_key, {})
    for logical_name, rel_path in page_files.items():
        if logical_name in routes:
            # Prefer hand-written role-specific descriptions when available,
            # fall back to stripped HTML snapshots otherwise.
            text = role_pages.get(logical_name)
            if not text:
                text = _load_page_text(rel_path)
            pages[logical_name] = text

    user_context = {
        "role": role,
        "current_path": current_path,
        "routes": routes,
        "pages": pages,
    }

    try:
        answer = get_navigation_help(question, user_context)
        return jsonify({"answer": answer}), 200
    except RuntimeError as e:
        # Configuration error (e.g. missing API key)
        current_app.logger.exception("AI assistant configuration error")
        return (
            jsonify(
                {
                    "error": str(e),
                }
            ),
            500,
        )
    except Exception:
        current_app.logger.exception("AI assistant processing error")
        return (
            jsonify(
                {
                    "error": "Assistant is temporarily unavailable.",
                }
            ),
            500,
        )


