from pydantic import BaseModel, EmailStr, HttpUrl
from datetime import datetime
from typing import Optional


class CameraBase(BaseModel):
    """Base schema for camera email mapping"""
    camera_id: str
    email: EmailStr
    camera_url: Optional[str] = None


class CameraCreate(CameraBase):
    """Schema for creating a camera email mapping"""
    pass


class CameraUpdate(BaseModel):
    """Schema for updating a camera email mapping"""
    email: Optional[EmailStr] = None
    camera_url: Optional[str] = None


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

