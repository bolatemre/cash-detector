from typing import List, Dict, Any, Optional
from services.notifications.base import NotificationChannel, NotificationData
from services.notifications.email_channel import EmailNotificationChannel
from config.settings import settings
import logging

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Central notification service that manages multiple notification channels.
    
    This service allows sending notifications through multiple channels (Email, SMS, etc.)
    and makes it easy to add new channels in the future.
    """
    
    def __init__(self):
        self.channels: Dict[str, NotificationChannel] = {}
        self._initialize_channels()
    
    def _initialize_channels(self):
        """Initialize available notification channels"""
        # Email channel (always available)
        try:
            email_channel = EmailNotificationChannel()
            self.register_channel('email', email_channel)
            logger.info("Email notification channel registered")
        except Exception as e:
            logger.error(f"Failed to initialize email channel: {e}")
        
        # Future channels can be added here when needed:
        # Example: SMS, Telegram, Push notifications, etc.
    
    def register_channel(self, channel_name: str, channel: NotificationChannel):
        """Register a new notification channel."""
        self.channels[channel_name.lower()] = channel
        logger.info(f"Registered notification channel: {channel_name}")
    
    def get_channel(self, channel_name: str) -> Optional[NotificationChannel]:
        """Get a specific notification channel."""
        return self.channels.get(channel_name.lower())
    
    def get_available_channels(self) -> List[str]:
        """Get list of all registered channels."""
        return list(self.channels.keys())
    
    def get_enabled_channels(self) -> List[str]:
        """Get list of enabled channels."""
        return [name for name, channel in self.channels.items() if channel.is_enabled()]
    
    def send_notification(
        self,
        event_data: NotificationData,
        channels: List[str] = None,
        recipients: Dict[str, List[str]] = None
    ) -> Dict[str, bool]:
        """
        Send notification through specified channels.
        
        Args:
            event_data: NotificationData object with event information
            channels: List of channel names to use (default: ['email'])
            recipients: Dict mapping channel names to recipient lists
            
        Returns:
            Dict mapping channel names to success status
        """
        if channels is None:
            channels = ['email']  # Default to email only
        
        if recipients is None:
            # Use default recipients from settings
            recipients = {
                'email': settings.recipients_list,
            }
        
        results = {}
        data_dict = event_data.to_dict()
        
        for channel_name in channels:
            channel_name = channel_name.lower()
            
            # Check if channel exists
            if channel_name not in self.channels:
                logger.warning(f"Channel not registered: {channel_name}")
                results[channel_name] = False
                continue
            
            # Get channel
            channel = self.channels[channel_name]
            
            # Check if channel is enabled
            if not channel.is_enabled():
                logger.warning(f"Channel is disabled: {channel_name}")
                results[channel_name] = False
                continue
            
            # Get recipients for this channel
            channel_recipients = recipients.get(channel_name, [])
            if not channel_recipients:
                logger.warning(f"No recipients for channel: {channel_name}")
                results[channel_name] = False
                continue
            
            # Send notification
            try:
                subject = f"Security Alert - {event_data.camera_id}"
                success = channel.send(channel_recipients, subject, data_dict)
                results[channel_name] = success
                
                if success:
                    logger.info(f"Notification sent via {channel_name} to {len(channel_recipients)} recipient(s)")
                else:
                    logger.error(f"Failed to send notification via {channel_name}")
                    
            except Exception as e:
                logger.error(f"Error sending notification via {channel_name}: {e}", exc_info=True)
                results[channel_name] = False
        
        return results
    
    def __repr__(self):
        enabled = self.get_enabled_channels()
        return f"<NotificationService channels={len(self.channels)} enabled={enabled}>"

