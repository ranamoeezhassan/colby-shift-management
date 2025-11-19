from flask import Blueprint

ai_bp = Blueprint(
    "ai",
    __name__,
    url_prefix="",  # API is mounted at /api/ai/...
    template_folder="templates",
    static_folder="static",
    static_url_path="/ai/static",
)

# Import routes so that they are registered with the blueprint
from . import routes  # noqa: E402,F401


