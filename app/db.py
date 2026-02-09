import os
from pymongo import MongoClient
from dotenv import load_dotenv
from .logger import logger

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")

try:
    if not MONGO_URI:
        logger.error("MONGO_URI not found in environment variables")
        raise ValueError("MONGO_URI not found")
        
    client = MongoClient(MONGO_URI)
    db = client.get_database() # Connect to the default database in URI
    
    # Create index
    db.tasks.create_index([("user_id", 1), ("date", 1)], unique=True)
    
    logger.info("MongoDB connected and index created")
except Exception as e:
    logger.error(f"MongoDB connection failed: {e}")
    raise e
