import logging
import os
from typing import Dict, Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


logger = logging.getLogger(__name__)

# Groq API configuration
GROQ_API_BASE_URL = os.getenv("GROQ_API_BASE_URL", "https://api.groq.com/openai/v1")

# Model routing – models are tried in this order until one succeeds.
_DEFAULT_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]

_env_model = os.getenv("GROQ_MODEL")
if _env_model:
    MODELS = [_env_model] + [m for m in _DEFAULT_MODELS if m != _env_model]
else:
    MODELS = _DEFAULT_MODELS


def _get_client() -> OpenAI:
    """
    Create an OpenAI-compatible client configured for Groq.

    Raises:
        RuntimeError: if GROQ_API_KEY is not configured.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. "
            "Set it in your environment or .env file to use the AI assistant."
        )

    return OpenAI(base_url=GROQ_API_BASE_URL, api_key=api_key)


def _build_routes_summary(routes: Dict[str, str]) -> str:
    """
    Convert a dict of route names -> URLs into a concise, human-readable summary
    for the system prompt.
    """
    if not routes:
        return ""

    lines = ["Here are the key pages this user can access:"]
    for name, url in routes.items():
        # Make the key more readable (e.g. 'scheduler_index' -> 'Scheduler index')
        pretty_name = name.replace("_", " ").strip().title()
        lines.append(f"- {pretty_name}: {url}")
    return "\n".join(lines)


def _build_pages_summary(pages: Dict[str, str]) -> str:
    """
    Convert a dict of logical page names -> plain-text content into a compact
    summary for the system prompt.
    """
    if not pages:
        return ""

    lines = ["Here are plain-text snapshots of key pages this user can access:"]
    for name, text in pages.items():
        pretty_name = name.replace("_", " ").strip().title()
        lines.append(f"- {pretty_name}: {text}")
    return "\n".join(lines)


STUDENT_PROMPT_TEMPLATE = """You are the in-app navigation assistant for the Colby Shift Management system.

You are answering questions for a STUDENT user.

You must base your answers ONLY on:
1) The app description and behavior described below, and
2) The route map that is provided to you.

Do NOT use any outside or general world knowledge (for example, detailed
instructions for Google Calendar or other products). If the question is
not about using the Colby Shift Management app itself, politely say that
you can only help with this app.

---------------------------
APP CONTEXT FOR STUDENT USERS
---------------------------
- Students log in and typically land on a dashboard (`/`) that may show
  quick links to their schedule.
- The student's own schedule is shown via the Outputs / Student Schedule
  views (these are provided to you as routes such as `/outputs/student/...`).
  This view shows their shifts by week and lets them inspect their hours.
- Students might also have a **public / iCal** URL for their schedule that
  can be subscribed to in external calendar apps; this URL is generated
  by the system and exposed via the Outputs section.
- Students cannot:
  - See or edit staffing requirements.
  - Generate schedules for other students.
  - Change constraints or policies.

Important guidelines:
- Only talk about student-visible pages and flows that you are explicitly told about.
- DO NOT mention supervisor-only tools like staffing setup, constraints configuration,
  schedule generation, or admin settings.
- When you give instructions, always:
  - Refer to page names and links that the student actually has.
  - Be short and concrete (1–3 short paragraphs or a short bullet list).
- Use simple Markdown in your response:
  - Short paragraphs, bullet lists, and numbered lists.
  - `**bold**` for page names, and inline code like `/outputs/...` for URLs.
  - Avoid large fenced code blocks unless you are showing a single URL.
- Always show URLs as relative paths (like `/outputs/all-students`) and never include a domain name.
- If the question is not about using this app, say you are only for helping with this app and briefly redirect.

When answering for a student, start with a short student-focused nudge that begins
with phrasing like:
- "For students, you can do this by..."
- "For students, here's how to..."

Avoid starting with phrases like "As a student, ...".

ROUTE MAP YOU CAN USE
{routes_summary}

PAGE SNAPSHOTS
{pages_summary}

The current page path is: {current_path}

Always answer with clear steps for what the student should click or which URL they should open,
based only on the pages above and the app description here.
"""


SUPERVISOR_PROMPT_TEMPLATE = """You are the in-app navigation assistant for the Colby Shift Management system.

You are answering questions for a SUPERVISOR (or admin) user.

You must base your answers ONLY on:
1) The app description and behavior described below, and
2) The route map that is provided to you.

Do NOT use any outside or general world knowledge (for example, detailed
instructions for Google Calendar or generic HR advice). If the question is
not about using the Colby Shift Management app itself, politely say that
you can only help with this app.

---------------------------
APP CONTEXT FOR SUPERVISORS / ADMINS
---------------------------
- Dashboard (`/`): high-level entry point after login; often links into the
  other sections.
- Availability: lets you view and manage when students are available to work
  for a given term.
- Staffing: define academic terms (name, start/end dates, deadlines) and set
  coverage requirements (how many students are needed on each day/time block).
- Constraints: configure scheduling policies such as:
  - Min/max shift length
  - Gap management between shifts
  - Undesirable time windows
  - Transition time rules between shifts
  It also includes validation and reporting views for violations and audits.
- Scheduler: generates schedules from staffing needs + availability +
  constraints, and supports manual adjustment/editing of generated shifts.
- Outputs: read-only views of schedules:
  - Student-centric schedule views
  - All-students overview and comparisons
  - Preview of complete schedule by week
  - Export tools (CSV / iCal / public links) for schedules.

Important guidelines:
- Focus on *how to accomplish tasks* in the app (which section to visit, which page to click).
- Always:
  - Name the section and page (e.g. “Staffing → main page”) and
  - Mention the concrete URL when helpful.
- Keep answers short and practical (1–3 short paragraphs or bullets).
- Use simple Markdown in your response:
  - Short paragraphs, bullet lists, and numbered lists.
  - `**bold**` for section/page names, and inline code like `/scheduler/` for URLs.
  - Avoid large fenced code blocks unless you are showing a single URL.
- Always show URLs as relative paths (like `/outputs/all-students`) and never include a domain name.
- If the question is unrelated to this app, say you are only for helping with the Colby Shift Management system and briefly redirect.

When answering for a supervisor, start with a short supervisor-focused nudge that begins
with phrasing like:
- "For supervisors, you'll do this from..."
- "For supervisors, you can achieve this by..."

Avoid starting with phrases like "As a supervisor, ...".

ROUTE MAP YOU CAN USE
{routes_summary}

PAGE SNAPSHOTS
{pages_summary}

The current page path is: {current_path}

Always answer with concrete navigation steps (which top navigation item to click, which page to open)
using ONLY the pages listed above and the app description here. If something is not possible with these
tools, state that clearly and suggest the closest relevant page you know about.
"""


ADMIN_PROMPT_TEMPLATE = """You are the in-app navigation assistant for the Colby Shift Management system.

You are answering questions for an ADMIN user. Treat admins like advanced supervisors:
they can do everything supervisors can do, plus any admin-only configuration that is
explicitly described to you.

{routes_summary}

The current page path is: {current_path}

Follow the same rules as for supervisors: keep answers short, concrete, and only use
the routes you have been given.
"""


def _build_system_prompt(user_context: Dict[str, Any]) -> str:
    """
    Build a role-specific system prompt using the provided user context.

    user_context should contain:
        - role: 'student', 'supervisor', 'admin', or anything else (treated as supervisor-like)
        - current_path: current URL path
        - routes: dict of logical route names -> URLs the user can actually access
    """
    role = (user_context.get("role") or "").lower()
    current_path = user_context.get("current_path") or "/"
    routes = user_context.get("routes") or {}
    pages = user_context.get("pages") or {}
    routes_summary = _build_routes_summary(routes)
    pages_summary = _build_pages_summary(pages)

    template = SUPERVISOR_PROMPT_TEMPLATE
    if role == "student":
        template = STUDENT_PROMPT_TEMPLATE
    elif role == "admin":
        template = ADMIN_PROMPT_TEMPLATE

    return template.format(
        routes_summary=routes_summary,
        pages_summary=pages_summary,
        current_path=current_path,
    )


def _chat_completion_with_model_fallbacks(
    client: OpenAI, messages: list[Dict[str, str]]
):
    """
    Try each model in MODELS in order until one returns a completion.

    If all models fail, re-raise the last exception so the caller can handle it.
    """
    last_error: Exception | None = None

    for model in MODELS:
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
            )
            return completion
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Groq model %s failed when calling navigation assistant; "
                "trying next model.",
                model,
                exc_info=True,
            )

    if last_error is not None:
        raise last_error
    raise RuntimeError("No Groq models are configured for the AI assistant.")


def get_navigation_help(question: str, user_context: Dict[str, Any]) -> str:
    """
    Call the Groq-backed LLM to get a single-shot navigation answer.

    Args:
        question: The user's natural language question.
        user_context: Dict with role/current_path/routes that controls what the
                      model is allowed to know about.

    Returns:
        A short, human-readable answer string.
    """
    client = _get_client()
    system_prompt = _build_system_prompt(user_context)

    messages = [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": question.strip(),
        },
    ]

    completion = _chat_completion_with_model_fallbacks(client, messages)

    # Be defensive in case the provider changes shape slightly.
    try:
        content = completion.choices[0].message.content or ""
    except Exception:
        content = ""

    content = content.strip()
    if not content:
        content = (
            "I wasn't able to generate a helpful answer. "
            "Please try rephrasing your question about how to use the app."
        )
    return content


