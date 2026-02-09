from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime

class TaskSave(BaseModel):
    status: Optional[str] = Field("Pending")
    assign_website: Optional[str] = ""
    task_assign_no: Optional[str] = ""
    other_tasks: Optional[str] = ""
    task_updates: Optional[str] = ""
    additional: Optional[str] = ""
    note: Optional[str] = ""
    total_pages_done: Optional[int] = 0

class TaskResponse(BaseModel):
    user_id: str
    owner_name: Optional[str]
    date: str
    planner: Optional[str]
    status: Optional[str]
    assign_website: Optional[str]
    task_assign_no: Optional[str]
    other_tasks: Optional[str]
    task_updates: Optional[str]
    additional: Optional[str]
    note: Optional[str]
    total_pages_done: Optional[int]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True
