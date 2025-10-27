from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class EventMessage(BaseModel):
    """Schema for event message received from Kafka"""
    
    event_type: str = Field(..., description="Type of event: suspicious or normal")
    camera_id: str = Field(..., description="ID of the camera")
    detected_at: datetime = Field(..., description="Timestamp when event was detected")
    video_url: Optional[str] = Field(None, description="Full URL to the video clip in MinIO")
    
    class Config:
        json_schema_extra = {
            "example": {
                "event_type": "suspicious",
                "camera_id": "CAM-001",
                "detected_at": "2025-10-15T14:30:00Z",
                "video_url": "http://localhost:9000/security-videos/events/event_20251015_143000.mp4"
            }
        }

