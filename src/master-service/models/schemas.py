from pydantic import BaseModel, EmailStr, HttpUrl
from datetime import datetime
from typing import Optional, List, Dict, Any


class CameraBase(BaseModel):
    """Base schema for camera email mapping"""
    camera_id: str
    email: EmailStr
    camera_url: Optional[str] = None
    expected_fps: Optional[int] = 25
    record_fps: Optional[int] = 20
    is_video: Optional[bool] = False
    buffersize: Optional[int] = 1


class CameraCreate(CameraBase):
    """Schema for creating a camera email mapping"""
    pass


class CameraUpdate(BaseModel):
    """Schema for updating a camera email mapping"""
    email: Optional[EmailStr] = None
    camera_url: Optional[str] = None
    expected_fps: Optional[int] = None
    record_fps: Optional[int] = None
    is_video: Optional[bool] = None
    buffersize: Optional[int] = None


class CameraResponse(CameraBase):
    """Schema for camera email response"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class EmailResponse(BaseModel):
    """Simple email response"""
    camera_id: str
    email: str


class CameraUrlResponse(BaseModel):
    """Camera URL response with FPS settings"""
    camera_id: str
    camera_url: Optional[str] = None
    expected_fps: Optional[int] = 25
    record_fps: Optional[int] = 20
    is_video: Optional[bool] = False
    buffersize: Optional[int] = 1


# Task-related schemas
class TaskInfo(BaseModel):
    """Information about a single task"""
    task_id: str
    name: Optional[str] = None
    args: Optional[List[Any]] = None
    kwargs: Optional[Dict[str, Any]] = None
    worker: Optional[str] = None
    time_start: Optional[float] = None


class CameraStreamTask(BaseModel):
    """Information about camera stream task"""
    task_id: str
    camera_id: str


class TaskStatusResponse(BaseModel):
    """Response for task status query"""
    task_id: str
    status: str  # PENDING, STARTED, SUCCESS, FAILURE, RETRY, REVOKED
    result: Optional[Any] = None
    traceback: Optional[str] = None


class ActiveTasksResponse(BaseModel):
    """Response containing active camera stream tasks"""
    active_tasks: List[CameraStreamTask]
    total_count: int


class TaskStopResponse(BaseModel):
    """Response for stopping a task"""
    status: str
    task_id: str
    message: str

