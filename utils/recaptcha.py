import os
import requests
from flask import current_app

def verify_recaptcha(response_token):
    """
    Verify reCAPTCHA response with Google's API.

    In local development / testing we want to be able to disable
    reCAPTCHA entirely so that missing tokens don't block login.
    """
    if current_app.debug or current_app.config.get('TESTING') or \
       os.environ.get('DISABLE_RECAPTCHA', '').lower() in {'1', 'true', 'yes'}:
        print("Debug: reCAPTCHA disabled (development/testing) - skipping verification")
        return True

    secret_key = current_app.config.get('RECAPTCHA_SECRET_KEY')
    if not secret_key:
        print("Warning: No RECAPTCHA_SECRET_KEY configured - skipping verification")
        return True

    if not response_token:
        return False
    
    print(f"Debug: Verifying reCAPTCHA with response: {response_token[:20]}..." if response_token else "Debug: No reCAPTCHA response provided")
    
    # Verify with Google's API
    try:
        response = requests.post(
            'https://www.google.com/recaptcha/api/siteverify',
            data={
                'secret': secret_key,
                'response': response_token
            },
            timeout=10
        )
        
        result = response.json()
        success = result.get('success', False)
        print(f"Debug: reCAPTCHA verification result: success={success}, errors={result.get('error-codes', [])}")
        return success
        
    except Exception as e:
        # Log error in production, but don't fail the request
        print(f"reCAPTCHA verification error: {e}")
        return False