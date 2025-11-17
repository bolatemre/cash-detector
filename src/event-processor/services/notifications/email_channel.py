import re
from typing import List, Dict, Any
from services.notifications.base import NotificationChannel
from services.email_service import EmailService
import logging

logger = logging.getLogger(__name__)


class EmailNotificationChannel(NotificationChannel):
    """
    Email notification channel implementation.
    Uses the existing EmailService for actual email sending.
    """
    
    def __init__(self):
        super().__init__("Email")
        self.email_service = EmailService()
        self._email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    
    def send(self, recipients: List[str], subject: str, data: Dict[str, Any]) -> bool:
        """
        Send email notification.
        
        Args:
            recipients: List of email addresses
            subject: Email subject (not used, generated based on event)
            data: Event data dictionary
            
        Returns:
            bool: True if email was sent successfully
        """
        if not self.is_enabled():
            logger.warning("Email channel is disabled, skipping notification")
            return False
        
        if not self.validate_recipients(recipients):
            logger.error(f"Invalid email recipients: {recipients}")
            return False
        
        try:
            # Extract data
            camera_id = data.get('camera_id')
            detected_at = data.get('detected_at')
            video_url = data.get('video_url')
            
            # Send via EmailService
            success = self.email_service.send_suspicious_event_notification(
                camera_id=camera_id,
                detected_at=detected_at,
                video_url=video_url,
                recipients=recipients
            )
            
            if success:
                logger.info(f"Email notification sent successfully to {len(recipients)} recipient(s)")
            else:
                logger.error(f"Failed to send email notification")
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending email notification: {e}", exc_info=True)
            return False
    
    def validate_recipients(self, recipients: List[str]) -> bool:
        """
        Validate email addresses.
        
        Args:
            recipients: List of email addresses
            
        Returns:
            bool: True if all emails are valid
        """
        if not recipients:
            logger.warning("No email recipients provided")
            return False
        
        for email in recipients:
            if not self._email_pattern.match(email):
                logger.error(f"Invalid email address: {email}")
                return False
        
        return True

