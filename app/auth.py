import jwt
import os
from datetime import datetime, timedelta
from .logger import logger

JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key-change-this")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24

def create_token(uid: str, email: str, role: str) -> str:
    """Create a JWT token for a user."""
    payload = {
        "uid": uid,
        "email": email,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": datetime.utcnow()
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    logger.info(f"Token created for user: {uid}")
    return token

def verify_token(token: str) -> dict:
    """Verify JWT token and return decoded payload."""
    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        logger.info(f"Token verified for user: {decoded.get('uid')}")
        return decoded
    except jwt.ExpiredSignatureError:
        logger.error("Token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.error(f"Token verification failed: {e}")
        return None
