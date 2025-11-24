import logging
from datetime import datetime
from sqlalchemy.orm import Session
from models.event import Event
from models.schemas import EventMessage
from services.notifications import NotificationService, NotificationData
from services.minio_service import MinioService
from services.master_service_client import MasterServiceClient
from config.settings import settings

logger = logging.getLogger(__name__)


class EventProcessor:
    """Processes events: saves to database and sends notifications"""
    
    def __init__(self, db_session: Session, notification_service: NotificationService, minio_service: MinioService, master_service_client: MasterServiceClient = None):
        self.db_session = db_session
        self.notification_service = notification_service
        self.minio_service = minio_service
        self.master_service_client = master_service_client or MasterServiceClient(settings.master_service_url)
    
    def process_event(self, event_data: dict) -> bool:
        """
        Process incoming event from Kafka
        
        Args:
            event_data: Event data dictionary from Kafka
            
        Returns:
            bool: True if processing was successful
        """
        try:
            # Validate event data using Pydantic schema
            event_message = EventMessage(**event_data)
            
            # Extract video URL (now comes as full URL from AI service)
            video_url = event_message.video_url
            
            # Extract filename from URL if needed
            video_filename = None
            if video_url:
                # Get filename from URL: http://.../events/filename.mp4 -> filename.mp4
                video_filename = video_url.split('/')[-1] if '/' in video_url else None
            
            # Create event record
            event = Event(
                event_type=event_message.event_type,
                camera_id=event_message.camera_id,
                detected_at=event_message.detected_at,
                video_url=video_url,
                video_filename=video_filename
            )
            
            # Save to database
            self.db_session.add(event)
            self.db_session.commit()
            self.db_session.refresh(event)
            
            logger.info(f"Event saved to database: {event.id}")
            
            # Process suspicious events
            if event.event_type.lower() == "suspicious":
                # Move video to suspicious folder in MinIO
                if event.video_url:
                    try:
                        logger.info(f"Moving video to suspicious folder for event {event.id}")
                        new_video_url = self.minio_service.move_video_to_suspicious(event.video_url)
                        
                        # Update event with new video URL
                        if new_video_url != event.video_url:
                            event.video_url = new_video_url
                            # Update filename if changed
                            if new_video_url:
                                event.video_filename = new_video_url.split('/')[-1] if '/' in new_video_url else None
                            self.db_session.commit()
                            self.db_session.refresh(event)
                            logger.info(f"Video moved and URL updated: {new_video_url}")
                    except Exception as e:
                        logger.error(f"Error moving video to suspicious folder: {e}", exc_info=True)
                        # Continue with notification even if video move fails
                
                # Send notification
                self._send_notification(event)
            else:
                logger.info(f"Event {event.id} is not suspicious, skipping notification and video move")
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing event: {e}", exc_info=True)
            self.db_session.rollback()
            return False
    
    def _convert_to_public_url(self, video_url: str) -> str:
        """
        Convert internal MinIO URL to public URL for email notifications
        
        Args:
            video_url: Internal video URL (e.g., http://minio:9000/bucket/path)
            
        Returns:
            str: Public video URL for external access
        """
        if not video_url or not settings.minio_public_url:
            return video_url
        
        # Replace internal endpoint with public URL
        # Internal: http://minio:9000/security-videos/suspicious/video.mp4
        # Public: http://localhost:9000/security-videos/suspicious/video.mp4
        
        # Parse and replace the endpoint part
        if settings.minio_endpoint in video_url:
            public_url = video_url.replace(settings.minio_endpoint, settings.minio_public_url)
            logger.debug(f"Converted URL: {video_url} -> {public_url}")
            return public_url
        
        # Also handle cases where URL might have http:// prefix in endpoint
        internal_url_variations = [
            f"http://{settings.minio_endpoint}",
            f"https://{settings.minio_endpoint}",
            settings.minio_endpoint
        ]
        
        for internal_url in internal_url_variations:
            if internal_url in video_url:
                public_url = video_url.replace(internal_url, settings.minio_public_url)
                logger.debug(f"Converted URL: {video_url} -> {public_url}")
                return public_url
        
        return video_url
    
    def _send_notification(self, event: Event) -> bool:
        """
        Send notification for suspicious event through configured channels
        
        Args:
            event: Event database object
            
        Returns:
            bool: True if notification was sent successfully through at least one channel
        """
        try:
            # Get email address for this camera from master-service
            email = self.master_service_client.get_email_by_camera_id(event.camera_id)
            
            if not email:
                logger.error(f"No email found for camera {event.camera_id}, skipping notification")
                return False
            
            logger.info(f"Retrieved email for camera {event.camera_id}: {email}")
            
            if not event.video_url:
                logger.warning(f"Event {event.id} has no video URL, notification may be incomplete")
                video_url = "Video not available"
            else:
                # Convert internal URL to public URL for email notification
                video_url = self._convert_to_public_url(event.video_url)
            
            # Create notification data
            notification_data = NotificationData(
                event_id=event.id,
                event_type=event.event_type,
                camera_id=event.camera_id,
                detected_at=event.detected_at,
                video_url=video_url
            )
            
            # Send through configured channels with camera-specific email
            # Channels are configured via NOTIFICATION_CHANNELS env variable
            # Example: NOTIFICATION_CHANNELS=email,sms,telegram
            results = self.notification_service.send_notification(
                event_data=notification_data,
                channels=settings.channels_list,  # From .env configuration
                recipients={'email': [email]}  # Use email from master-service
            )
            
            # Check if at least one channel succeeded
            success = any(results.values())
            
            if success:
                # Update notification status
                event.notification_sent = True
                event.notification_sent_at = datetime.utcnow()
                self.db_session.commit()
                logger.info(f"Notification sent for event {event.id} to {email} via channels: {[k for k, v in results.items() if v]}")
            else:
                logger.error(f"Failed to send notification for event {event.id} through any channel")
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending notification for event {event.id}: {e}", exc_info=True)
            return False

