from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .auth import verify_token
from .db import db
from .logger import logger

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Verifies JWT token, checks if user exists in MongoDB, and returns user document.
    """
    token = credentials.credentials
    decoded_token = verify_token(token)
    
    if not decoded_token:
         raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    uid = decoded_token.get("uid")
    user = db.users.find_one({"uid": uid})
    
    if not user:
        logger.warning(f"Token valid but user NOT found in MongoDB: {uid}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found in database",
        )

    # Attach email from token if missing
    if not user.get("email"):
        user["email"] = decoded_token.get("email")

    return user

async def require_user(user: dict = Depends(get_current_user)):
    """Allows 'user' or 'admin' roles."""
    role = user.get("role")
    if role not in ["user", "admin"]:
        logger.warning(f"Access denied for user {user.get('uid')} with role {role}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return user

async def require_admin(user: dict = Depends(get_current_user)):
    """Allows only 'admin' role."""
    role = user.get("role")
    if role != "admin":
        logger.warning(f"Admin access denied for user {user.get('uid')} with role {role}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return user
