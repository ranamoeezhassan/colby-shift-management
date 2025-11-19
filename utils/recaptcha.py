import requests
from flask import current_app

def verify_recaptcha(response_token):
    """
    Verify reCAPTCHA response with Google's API
    
    Args:
        response_token (str): The reCAPTCHA response token from the client
        
    Returns:
        bool: True if verification successful, False otherwise
    """
    if not response_token:
        return False
    
    # Get secret key from config
    secret_key = current_app.config.get('RECAPTCHA_SECRET_KEY')
    if not secret_key:
        # If no secret key configured, skip verification (for development)
        return True
    
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
        return result.get('success', False)
        
    except Exception as e:
        # Log error in production, but don't fail the request
        print(f"reCAPTCHA verification error: {e}")
        return False