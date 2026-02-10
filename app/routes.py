from fastapi import APIRouter, Depends, HTTPException, Query, Body
from datetime import datetime
from typing import List, Optional
from bson import ObjectId

from .logger import logger
from .deps import get_current_user, require_user, require_admin
from .db import db
from .schemas import TaskSave, TaskResponse

router = APIRouter()

# --- Utility ---
def get_today_str():
    return datetime.utcnow().strftime("%Y-%m-%d")

def get_day_name(date_str):
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%A")

# --- Auth Routes (Kept for verification) ---
@router.get("/health")
async def health_check():
    return {"status": "ok"}

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
        # logger.info(f"Task found for user {uid} on {target_date}")
        return {"exists": True, "task": task}
    else:
        # logger.info(f"No task found for user {uid} on {target_date}")
        return {"exists": False, "task": None}

@router.get("/api/tasks/previous")
async def get_previous_task(
    before_date: Optional[str] = Query(None),
    user: dict = Depends(require_user)
):
    """Get the most recent task strictly BEFORE the given date (default today)."""
    target_date = before_date or get_today_str()
    uid = user["uid"]
    
    # Find latest task where date < target_date
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
    
    # Use date from payload if provided, else today
    target_date = task_data.date or today
    day_name = get_day_name(target_date)
    
    # Prepare update data
    update_doc = task_data.dict(exclude_unset=True)
    if "date" in update_doc:
        del update_doc["date"] # Don't update the date field itself inside the doc structure if it's the key
        
    update_doc["updated_at"] = datetime.utcnow()
    
    # On insert only fields
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
    """Admin: Update any task by user_id and date."""
    # Using user_id + date as key since _id is hidden/mixed
    
    task_update["updated_at"] = datetime.utcnow()
    
    result = db.tasks.update_one(
        {"user_id": user_id, "date": date},
        {"$set": task_update}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
        
    logger.info(f"Admin {admin['uid']} updated task for {user_id} on {date}")
    return {"message": "Task updated"}

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
        
from firebase_admin import auth

# --- User Creation (Admin Only) ---
@router.post("/api/admin/create-user")
async def create_user(
    user_data: dict = Body(...),
    admin: dict = Depends(require_admin)
):
    """Create a new user in Firebase and MongoDB."""
    email = user_data.get("email")
    password = user_data.get("password")
    name = user_data.get("name")
    
    if not email or not password or not name:
        raise HTTPException(status_code=400, detail="Missing fields")
        
    try:
        # Create in Firebase
        user = auth.create_user(
            email=email,
            password=password,
            display_name=name
        )
        
        # Insert into MongoDB
        new_user = {
            "uid": user.uid,
            "email": email,
            "name": name,
            "password": password,  # Storing plain text password as requested
            "role": "user",
            "created_at": datetime.utcnow(),
            "is_active": True
        }
        
        db.users.insert_one(new_user)
        
        logger.info(f"Admin {admin['uid']} created new user {email} ({user.uid})")
        return {"message": "User created successfully", "uid": user.uid}
        
    except Exception as e:
        logger.error(f"Failed to create user: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/api/admin/users")
async def get_all_users(admin: dict = Depends(require_admin)):
    """Get all users (excluding admins)."""
    # Exclude users with role='admin'
    users = list(db.users.find({"role": {"$ne": "admin"}}, {"_id": 0}))
    return users

@router.delete("/api/admin/user/{uid}")
async def delete_user(uid: str, admin: dict = Depends(require_admin)):
    """Delete a user from Firebase and MongoDB."""
    try:
        # 1. Delete from Firebase
        auth.delete_user(uid)
        
        # 2. Delete from MongoDB
        db.users.delete_one({"uid": uid})
        
        logger.info(f"Admin {admin['uid']} deleted user {uid}")
        return {"message": "User deleted successfully"}
        
    except Exception as e:
        logger.error(f"Failed to delete user {uid}: {e}")
        raise HTTPException(status_code=400, detail=str(e))


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
    
    # 1. Fetch tasks
    cursor = db.tasks.find(query, {"_id": 0}).sort("date", -1)
    tasks = list(cursor)
    
    if not tasks:
        raise HTTPException(status_code=404, detail="No tasks found")
        
    # 2. Convert to DataFrame
    df = pd.DataFrame(tasks)
    
    # 3. Select and Reorder Columns (Optional: match frontend)
    # Ensure all expected columns exist even if empty
    expected_cols = [
        "date", "owner_name", "user_id", "status", 
        "total_pages_done", "assign_website", "task_updates",
        "planner", "task_assign_no", "other_tasks", "additional", "note"
    ]
    
    for col in expected_cols:
        if col not in df.columns:
            df[col] = ""
            
    # Reorder
    df = df[expected_cols]
    
    # 4. Write to BytesIO buffer
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name="Tasks")
        
    output.seek(0)
    
    # 5. Return StreamingResponse
    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"'
    }
    
    return StreamingResponse(output, headers=headers, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
