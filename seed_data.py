import firebase_admin
from firebase_admin import credentials, auth
from pymongo import MongoClient
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import random

# Load .env
load_dotenv(dotenv_path=".env")

# Init Firebase
cred_path = os.path.join(os.getcwd(), "serviceAccountKey.json")
if not os.path.exists(cred_path):
    # Try alternate path if running from root vs backend
    cred_path = os.path.join(os.getcwd(), "backend", "serviceAccountKey.json")

if not os.path.exists(cred_path):
    print(f"Error: serviceAccountKey.json not found at {cred_path}")
    exit(1)

if not firebase_admin._apps:
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)

# Init Mongo
mongo_uri = os.getenv("MONGO_URI")
if not mongo_uri:
    print("MONGO_URI not found in .env")
    exit(1)

client = MongoClient(mongo_uri)
db = client.get_database() 

EMAIL = "mohit1234@gmail.com"
NAME = "Mohit Test"
PASSWORD = "password123"

def seed_data():
    # 1. Get or Create User
    try:
        user = auth.get_user_by_email(EMAIL)
        uid = user.uid
        print(f"Found existing user: {EMAIL} ({uid})")
    except auth.UserNotFoundError:
        print(f"Creating new user: {EMAIL}")
        user = auth.create_user(
            email=EMAIL,
            password=PASSWORD,
            display_name=NAME
        )
        uid = user.uid
        
    # Ensure role is user in Mongo
    db.users.update_one(
        {"uid": uid},
        {"$set": {"email": EMAIL, "name": NAME, "role": "user", "uid": uid}},
        upsert=True
    )

    # 2. Insert 3 days of past data
    today = datetime.utcnow().date()
    
    tasks = []
    
    # Generate for (Today-3) to (Today-1)
    for i in range(1, 4):
        past_date = today - timedelta(days=i)
        date_str = past_date.isoformat()
        
        # Check if exists
        existing = db.tasks.find_one({"user_id": uid, "date": date_str})
        if existing:
            print(f"Task for {date_str} already exists. Skipping.")
            continue
            
        task = {
            "user_id": uid,
            "owner_name": NAME,
            "date": date_str,
            "planner": past_date.strftime("%A"),
            "status": random.choice(["Completed", "In Progress", "Pending"]),
            "assign_website": random.choice(["FleetRabbit", "HeavyVehicleInspection", "Oxmaint"]),
            "task_assign_no": f"{random.randint(5, 15)} pages",
            "other_tasks": "Research on " + random.choice(["SEO", "Competitors", "Keywords"]),
            "task_updates": f"Worked on {date_str}. Updated meta tags and content structure. Reference: https://example.com/doc-{i}",
            "additional": "None",
            "note": "",
            "total_pages_done": random.randint(3, 12),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        tasks.append(task)
        
    if tasks:
        db.tasks.insert_many(tasks)
        print(f"Successfully inserted {len(tasks)} mock tasks for {EMAIL}")
    else:
        print("No new tasks to insert.")

if __name__ == "__main__":
    seed_data()
