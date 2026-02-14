from fastapi import APIRouter, Depends, HTTPException, Query, Body
from datetime import datetime
from typing import List, Optional
from bson import ObjectId
import uuid

from .logger import logger
from .deps import get_current_user, require_user, require_admin
from .db import db
from .schemas import TaskSave, TaskResponse
from .auth import create_token

router = APIRouter()

# --- Utility ---
def get_today_str():
    return datetime.utcnow().strftime("%Y-%m-%d")

def get_day_name(date_str):
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%A")

# --- Auth Routes ---

@router.get("/health")
async def health_check():
    return {"status": "ok"}

@router.post("/api/login")
async def login(credentials: dict = Body(...)):
    """Authenticate user with email and password, return JWT token."""
    email = credentials.get("email", "").strip().lower()
    password = credentials.get("password", "").strip()
    
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")
    
    # Find user in MongoDB
    user = db.users.find_one({"email": email})
    
    if not user:
        logger.warning(f"Login failed: user not found - {email}")
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Check password (plain text comparison as per user preference)
    stored_password = user.get("password", "")
    if password != stored_password:
        logger.warning(f"Login failed: wrong password - {email}")
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Generate JWT token
    token = create_token(
        uid=user["uid"],
        email=user["email"],
        role=user.get("role", "user")
    )
    
    logger.info(f"User logged in: {email}")
    return {
        "token": token,
        "uid": user["uid"],
        "email": user["email"],
        "role": user.get("role", "user"),
        "name": user.get("name", "")
    }

@router.get("/api/me")
async def get_me(user: dict = Depends(get_current_user)):
    return {"uid": user.get("uid"), "email": user.get("email"), "role": user.get("role")}

# --- User Task APIs ---

@router.get("/api/tasks/today")
async def get_today_task(
    date: Optional[str] = Query(None),
    user: dict = Depends(require_user)
):
    """Get current user's task for today (or specific date)."""
    target_date = date or get_today_str()
    uid = user["uid"]
    
    task = db.tasks.find_one({"user_id": uid, "date": target_date}, {"_id": 0})
    
    if task:
        return {"exists": True, "task": task}
    else:
        # Task doesn't exist -> Check if User has persistent assignments
        user_doc = db.users.find_one({"uid": uid})
        default_task = None
        
        if user_doc:
            # Construct a template task with persistent values
            default_task = {
                "date": target_date,
                "assign_website": user_doc.get("assign_website", ""),
                "task_assign_no": user_doc.get("task_assign_no", ""),
                "other_tasks": user_doc.get("other_tasks", ""),
                "status": "Not Started",
                "total_pages_done": 0
            }
            
        return {"exists": False, "task": default_task}

@router.get("/api/tasks/previous")
async def get_previous_task(
    before_date: Optional[str] = Query(None),
    user: dict = Depends(require_user)
):
    """Get the most recent task strictly BEFORE the given date (default today)."""
    target_date = before_date or get_today_str()
    uid = user["uid"]
    
    task = db.tasks.find_one(
        {"user_id": uid, "date": {"$lt": target_date}},
        sort=[("date", -1)]
    )
    
    if task:
        if "_id" in task: del task["_id"]
        return {"exists": True, "task": task}
    else:
        return {"exists": False, "task": None}

@router.post("/api/tasks/save")
async def save_task(task_data: TaskSave, user: dict = Depends(require_user)):
    """Upsert task for today (or specific date)."""
    uid = user["uid"]
    today = get_today_str()
    
    target_date = task_data.date or today
    day_name = get_day_name(target_date)
    
    update_doc = task_data.dict(exclude_unset=True)
    if "date" in update_doc:
        del update_doc["date"]
        
    update_doc["updated_at"] = datetime.utcnow()
    
    insert_doc = {
        "user_id": uid,
        "date": target_date,
        "owner_name": user.get("name") or user.get("email", "Unknown"),
        "planner": day_name,
        "created_at": datetime.utcnow()
    }
    
    result = db.tasks.update_one(
        {"user_id": uid, "date": target_date},
        {
            "$set": update_doc,
            "$setOnInsert": insert_doc
        },
        upsert=True
    )
    
    logger.info(f"Task saved for user {uid} on {target_date}.")
    return {"message": "Task saved"}

@router.get("/api/tasks/history")
async def get_task_history(
    limit: int = Query(30, ge=1, le=100),
    user: dict = Depends(require_user)
):
    """Get task history for current user."""
    uid = user["uid"]
    
    cursor = db.tasks.find({"user_id": uid}, {"_id": 0}).sort("date", -1).limit(limit)
    tasks = list(cursor)
    
    logger.info(f"Fetched {len(tasks)} history items for user {uid}")
    return tasks

# --- Admin APIs ---

@router.get("/api/admin/tasks")
async def get_all_tasks(
    date: Optional[str] = None,
    user_uid: Optional[str] = Query(None, alias="user"),
    limit: int = 100,
    admin: dict = Depends(require_admin)
):
    """Admin: Get all tasks with optional filtering."""
    query = {}
    if date:
        query["date"] = date
    if user_uid:
        query["user_id"] = user_uid
        
    cursor = db.tasks.find(query, {"_id": 0}).sort("date", -1).limit(limit)
    tasks = list(cursor)
    
    logger.info(f"Admin {admin['uid']} fetched {len(tasks)} tasks")
    return tasks

@router.put("/api/admin/task/{user_id}/{date}")
async def admin_update_task(
    user_id: str,
    date: str,
    task_update: dict = Body(...),
    admin: dict = Depends(require_admin)
):
    """Admin: Update (or create) any task by user_id and date."""
    task_update["updated_at"] = datetime.utcnow()
    
    # Try to update first
    result = db.tasks.update_one(
        {"user_id": user_id, "date": date},
        {"$set": task_update}
    )
    
    # If no document matched, check if we should create one (Upsert logic)
    if result.matched_count == 0:
        # Fetch user details to create a proper task document
        user = db.users.find_one({"uid": user_id})
        if not user:
             raise HTTPException(status_code=404, detail="User not found to assign task to")
             
        new_task = {
            "user_id": user_id,
            "date": date,
            "owner_name": user.get("name", "Unknown"),
            "planner": f"Admin ({admin.get('name', 'Admin')})",
            "status": "Not Started",
            "assign_website": "",
            "task_assign_no": "",
            "other_tasks": "",
            "task_updates": "",
            "additional": "",
            "note": "",
            "total_pages_done": 0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        # Overlay the updates
        new_task.update(task_update)
        
        db.tasks.insert_one(new_task)
        
        # PERSISTENCE: Save assignments to User profile as well
        user_updates = {}
        if "assign_website" in task_update: user_updates["assign_website"] = task_update["assign_website"]
        if "task_assign_no" in task_update: user_updates["task_assign_no"] = task_update["task_assign_no"]
        if "other_tasks" in task_update: user_updates["other_tasks"] = task_update["other_tasks"]
        
        if user_updates:
            db.users.update_one({"uid": user_id}, {"$set": user_updates})
            
        logger.info(f"Admin {admin['email']} created new task for {user['email']} on {date}")
        return {"message": "Task created successfully"}
    
    # Update matched -> Also update User persistence
    user_updates = {}
    if "assign_website" in task_update: user_updates["assign_website"] = task_update["assign_website"]
    if "task_assign_no" in task_update: user_updates["task_assign_no"] = task_update["task_assign_no"]
    if "other_tasks" in task_update: user_updates["other_tasks"] = task_update["other_tasks"]
    
    if user_updates:
        db.users.update_one({"uid": user_id}, {"$set": user_updates})
        
    logger.info(f"Admin {admin['email']} updated task for user {user_id} on {date}")
    return {"message": "Task updated successfully"}

@router.delete("/api/admin/task/{user_id}/{date}")
async def admin_delete_task(
    user_id: str,
    date: str,
    admin: dict = Depends(require_admin)
):
    """Admin: Delete task."""
    result = db.tasks.delete_one({"user_id": user_id, "date": date})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")

# --- User Creation (Admin Only) ---
@router.post("/api/admin/create-user")
async def create_user(
    user_data: dict = Body(...),
    admin: dict = Depends(require_admin)
):
    """Create a new user in MongoDB."""
    email = user_data.get("email", "").strip().lower()
    password = user_data.get("password", "").strip()
    name = user_data.get("name", "").strip()
    
    if not email or not password or not name:
        raise HTTPException(status_code=400, detail="Missing fields")
    
    # Check if user already exists
    existing = db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="User with this email already exists")
    
    # Generate unique ID
    uid = str(uuid.uuid4())
    
    new_user = {
        "uid": uid,
        "email": email,
        "name": name,
        "password": password,  # Plain text as per admin preference
        "role": "user",
        "created_at": datetime.utcnow(),
        "is_active": True
    }
    
    db.users.insert_one(new_user)
    
    logger.info(f"Admin {admin['uid']} created new user {email} ({uid})")
    return {"message": "User created successfully", "uid": uid}

@router.get("/api/admin/users")
async def get_all_users(admin: dict = Depends(require_admin)):
    """Get all users (excluding admins)."""
    users = list(db.users.find({"role": {"$ne": "admin"}}, {"_id": 0}))
    return users

@router.delete("/api/admin/user/{uid}")
async def delete_user(uid: str, admin: dict = Depends(require_admin)):
    """Delete a user from MongoDB."""
    try:
        # Delete from MongoDB
        result = db.users.delete_one({"uid": uid})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="User not found")
        
        logger.info(f"Admin {admin['uid']} deleted user {uid}")
        return {"message": "User deleted successfully"}
        
    except Exception as e:
        logger.error(f"Failed to delete user {uid}: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/api/admin/user/{uid}/password")
async def admin_reset_password(
    uid: str, 
    password_data: dict = Body(...), 
    admin: dict = Depends(require_admin)
):
    """Admin: Reset user password."""
    new_password = password_data.get("password")
    if not new_password or len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
        
    result = db.users.update_one(
        {"uid": uid},
        {"$set": {"password": new_password}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
        
    logger.info(f"Admin {admin['uid']} reset password for user {uid}")
    return {"message": "Password updated successfully"}


# --- Export APIs ---

import pandas as pd
from io import BytesIO
from fastapi.responses import StreamingResponse

@router.get("/api/admin/export/tasks")
async def export_tasks(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    admin: dict = Depends(require_admin)
):
    """Export tasks to Excel. If date provided, filter by date."""
    
    query = {}
    if date:
        query["date"] = date
        filename = f"tasks_{date}.xlsx"
    else:
        filename = f"tasks_all_{get_today_str()}.xlsx"
    
    cursor = db.tasks.find(query, {"_id": 0}).sort("date", -1)
    tasks = list(cursor)
    
    if not tasks:
        raise HTTPException(status_code=404, detail="No tasks found")
        
    df = pd.DataFrame(tasks)
    
    expected_cols = [
        "date", "owner_name", "user_id", "status", 
        "total_pages_done", "assign_website", "task_updates",
        "planner", "task_assign_no", "other_tasks", "additional", "note"
    ]
    
    for col in expected_cols:
        if col not in df.columns:
            df[col] = ""
            
    df = df[expected_cols]
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name="Tasks")
        
    output.seek(0)
    
    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"'
    }
    
    return StreamingResponse(output, headers=headers, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
