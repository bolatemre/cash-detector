from sqlalchemy import Column, String, DateTime, Text, Boolean, Integer
from sqlalchemy.sql import func
from database import Base
from config.settings import settings
import uuid


class Event(Base):
    """Model for suspicious events detected by the AI system"""
    
    __tablename__ = "events"
    __table_args__ = {'schema': settings.database_schema}
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Event classification
    event_type = Column(String(50), nullable=False)  # e.g., "suspicious", "cash_register", "change")
    
    # Event metadata
    camera_id = Column(String(100), nullable=False)
    detected_at = Column(DateTime(timezone=True), nullable=False)
    
    # Video information
    video_url = Column(Text, nullable=True)  # URL to the video clip
    video_filename = Column(String(255), nullable=True)  # Filename of the video clip
    
    # Notification status
    notification_sent = Column(Boolean, default=False)
    notification_sent_at = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<Event {self.id} - {self.event_type} - {self.camera_id}>"

