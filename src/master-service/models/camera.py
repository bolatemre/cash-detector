from sqlalchemy import Column, String, DateTime, Integer
from sqlalchemy.sql import func
from database import Base
from config.settings import settings


class Camera(Base):
    """Model for camera to email mapping"""
    
    __tablename__ = "camera_emails"
    __table_args__ = {'schema': settings.database_schema}
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    camera_id = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), nullable=False)
    camera_url = Column(String(500), nullable=True)  # Camera stream/access URL
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<Camera {self.camera_id} -> {self.email}>"

