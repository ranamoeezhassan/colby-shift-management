from flask import Blueprint
import os

from authlib.integrations.flask_client import OAuth

auth_bp = Blueprint(
    'auth',
    __name__,
    template_folder='templates',
    static_folder='static',
    static_url_path='/auth/static',
)

# OAuth client for this blueprint/package.
# Note: we don't bind it to the app here to avoid circular imports.
oauth = OAuth()


def init_google_oauth(app):
    """
    Configure Google OAuth on the given Flask app.

    This keeps provider-specific configuration close to the auth blueprint
    while still initializing the extension with the application instance.
    """
    google_client_id = os.environ.get('GOOGLE_CLIENT_ID')
    google_client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')

    if not google_client_id or not google_client_secret:
        # App still runs fine; Google login just won't be available.
        app.logger.info(
            "Google OAuth is not fully configured. "
            "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in your "
            "environment to enable it."
        )
        return

    # Bind the OAuth client to this app and register the Google provider.
    oauth.init_app(app)
    oauth.register(
        name='google',
        client_id=google_client_id,
        client_secret=google_client_secret,
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'},
    )
