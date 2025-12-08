from sqlalchemy import Column, String, DateTime, Integer, Boolean
from sqlalchemy.sql import func
from database import Base
from config.settings import settings


class Camera(Base):
    """Model for camera to email mapping"""
    
    __tablename__ = "camera"
    __table_args__ = {'schema': settings.database_schema}
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    camera_id = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), nullable=False)
    camera_url = Column(String(500), nullable=True)  # Camera stream/access URL
    expected_fps = Column(Integer, nullable=True, default=25)  # Expected FPS for processing
    record_fps = Column(Integer, nullable=True, default=20)  # FPS for video recording
    is_video = Column(Boolean, nullable=False, default=False)  # True if camera_url is a video file, False if it's a stream
    buffersize = Column(Integer, nullable=True, default=1)  # Buffer size for video capture (minimize buffer to get latest frame)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<Camera {self.camera_id} -> {self.email}>"

