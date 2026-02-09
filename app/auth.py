from firebase_admin import auth
from .logger import logger

def verify_token(token: str) -> dict:
    """Verifies Firebase ID token and returns decoded payload."""
    try:
        decoded_token = auth.verify_id_token(token)
        logger.info(f"Token verified for user: {decoded_token.get('uid')}")
        return decoded_token
    except Exception as e:
        logger.error(f"Token verification failed: {e}")
        return None
