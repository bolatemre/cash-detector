import logging
from datetime import datetime
from sqlalchemy.orm import Session
from urllib.parse import urlparse, quote
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
        Convert internal MinIO URL to MinIO API preview URL for email notifications
        
        Generates URL in format:
        https://minio-public-url/api/v1/buckets/{bucket}/objects/download?preview=true&prefix={object_path}&version_id=null
        
        Args:
            video_url: Internal video URL (e.g., http://minio:9000/security-videos/suspicious/video.mp4)
            
        Returns:
            str: MinIO API preview URL for video preview
        """
        if not video_url or not settings.minio_public_url:
            return video_url
        
        try:
            # Parse URL to extract bucket and object path
            # Example: http://minio:9000/security-videos/suspicious/video.mp4
            parsed = urlparse(video_url)
            path = parsed.path.lstrip('/')
            
            # Split path into bucket and object path
            # path = "security-videos/suspicious/video.mp4" -> bucket="security-videos", object_path="suspicious/video.mp4"
            path_parts = path.split('/', 1)
            
            if len(path_parts) == 2:
                bucket = path_parts[0]
                object_path = path_parts[1]
            else:
                # Fallback: use configured bucket if not in URL
                bucket = settings.minio_bucket
                object_path = path_parts[0] if path_parts else ''
            
            if not object_path:
                logger.warning(f"Could not extract object path from URL: {video_url}")
                return video_url
            
            # URL-encode the object path (e.g., "suspicious/video.mp4" -> "suspicious%2Fvideo.mp4")
            encoded_prefix = quote(object_path, safe='')
            
            # Remove trailing slash from public URL if present
            base_url = settings.minio_public_url.rstrip('/')
            
            # Build MinIO API preview URL
            # Format: https://minio-public-url/api/v1/buckets/{bucket}/objects/download?preview=true&prefix={object_path}&version_id=null
            preview_url = f"{base_url}/api/v1/buckets/{bucket}/objects/download?preview=true&prefix={encoded_prefix}&version_id=null"
            
            logger.debug(f"Generated preview URL: {video_url} -> {preview_url}")
            return preview_url
            
        except Exception as e:
            logger.error(f"Error generating preview URL: {e}", exc_info=True)
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

