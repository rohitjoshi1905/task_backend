import os
import json
import firebase_admin
from firebase_admin import credentials
from dotenv import load_dotenv
from .logger import logger

load_dotenv()

# Option 1: Full JSON string (Legacy/Alternative)
FIREBASE_CREDENTIALS_JSON = os.getenv("FIREBASE_CREDENTIALS_JSON")

# Option 2: Individual Vars
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID")
FIREBASE_PRIVATE_KEY = os.getenv("FIREBASE_PRIVATE_KEY")
FIREBASE_CLIENT_EMAIL = os.getenv("FIREBASE_CLIENT_EMAIL")

try:
    if not firebase_admin._apps:
        cred = None
        
        # Priority 1: Individual Variables (Cleanest)
        if FIREBASE_PROJECT_ID and FIREBASE_PRIVATE_KEY and FIREBASE_CLIENT_EMAIL:
            # Handle escaped newlines in private key if they come in as literal "\n"
            private_key = FIREBASE_PRIVATE_KEY.replace('\\n', '\n')
            
            cred_dict = {
                "type": "service_account",
                "project_id": FIREBASE_PROJECT_ID,
                "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID"),
                "private_key": private_key,
                "client_email": FIREBASE_CLIENT_EMAIL,
                "client_id": os.getenv("FIREBASE_CLIENT_ID"),
                "auth_uri": os.getenv("FIREBASE_AUTH_URI"),
                "token_uri": os.getenv("FIREBASE_TOKEN_URI"),
                "auth_provider_x509_cert_url": os.getenv("FIREBASE_AUTH_PROVIDER_X509_CERT_URL"),
                "client_x509_cert_url": os.getenv("FIREBASE_CLIENT_X509_CERT_URL"),
                "universe_domain": os.getenv("FIREBASE_UNIVERSE_DOMAIN")
            }
            cred = credentials.Certificate(cred_dict)
            
        # Priority 2: Full JSON String
        elif FIREBASE_CREDENTIALS_JSON:
            try:
                json_str = FIREBASE_CREDENTIALS_JSON.strip("'")
                cred_dict = json.loads(json_str)
                cred = credentials.Certificate(cred_dict)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse FIREBASE_CREDENTIALS_JSON: {e}")
                raise e
                
        # Priority 3: File Path (Fallback)
        elif os.getenv("FIREBASE_CREDENTIALS_PATH"):
             cred = credentials.Certificate(os.getenv("FIREBASE_CREDENTIALS_PATH"))
             
        else:
            logger.error("No valid Firebase credentials found in environment variables")
            raise ValueError("Firebase credentials not found")
            
        firebase_admin.initialize_app(cred)
        logger.info("Firebase initialized")
except Exception as e:
    logger.error(f"Firebase initialization failed: {e}")
    raise e
