from abc import ABC, abstractmethod
from typing import Dict, Any, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class NotificationChannel(ABC):
    """
    Abstract base class for notification channels.
    
    All notification channels (Email, SMS, Push, Telegram, etc.) 
    must inherit from this class and implement the send method.
    """
    
    def __init__(self, channel_name: str):
        self.channel_name = channel_name
        self.enabled = True
        logger.info(f"Notification channel initialized: {channel_name}")
    
    @abstractmethod
    def send(self, recipients: List[str], subject: str, data: Dict[str, Any]) -> bool:
        """
        Send notification through this channel.
        
        Args:
            recipients: List of recipient identifiers (emails, phones, user_ids, etc.)
            subject: Notification subject/title
            data: Dictionary with notification data
            
        Returns:
            bool: True if notification was sent successfully
        """
        pass
    
    @abstractmethod
    def validate_recipients(self, recipients: List[str]) -> bool:
        """
        Validate that recipients are in correct format for this channel.
        
        Args:
            recipients: List of recipient identifiers
            
        Returns:
            bool: True if all recipients are valid
        """
        pass
    
    def is_enabled(self) -> bool:
        """Check if this channel is enabled"""
        return self.enabled
    
    def enable(self):
        """Enable this notification channel"""
        self.enabled = True
        logger.info(f"Notification channel enabled: {self.channel_name}")
    
    def disable(self):
        """Disable this notification channel"""
        self.enabled = False
        logger.info(f"Notification channel disabled: {self.channel_name}")
    
    def __repr__(self):
        status = "enabled" if self.enabled else "disabled"
        return f"<{self.__class__.__name__} ({status})>"


class NotificationData:
    """
    Data Transfer Object for notification data.
    Standardizes data passed to notification channels.
    """
    
    def __init__(
        self,
        event_id: str,
        event_type: str,
        camera_id: str,
        detected_at: datetime,
        video_url: str
    ):
        self.event_id = event_id
        self.event_type = event_type
        self.camera_id = camera_id
        self.detected_at = detected_at
        self.video_url = video_url
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'event_id': self.event_id,
            'event_type': self.event_type,
            'camera_id': self.camera_id,
            'detected_at': self.detected_at,
            'video_url': self.video_url
        }
    
    def __repr__(self):
        return f"<NotificationData event_id={self.event_id} type={self.event_type}>"

