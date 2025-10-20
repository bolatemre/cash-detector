"""
MinIO Service for video file management
"""

import logging
from minio import Minio
from minio.error import S3Error
from minio.commonconfig import CopySource
from urllib.parse import urlparse
from config.settings import settings

logger = logging.getLogger(__name__)


class MinioService:
    """Service for managing video files in MinIO"""
    
    def __init__(self):
        """Initialize MinIO client"""
        # Parse endpoint to get host without protocol
        endpoint = settings.minio_endpoint.replace('http://', '').replace('https://', '')
        
        self.client = Minio(
            endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure
        )
        self.bucket = settings.minio_bucket
        self.suspicious_folder = settings.minio_suspicious_folder
        
        logger.info(f"MinIO service initialized: {endpoint}/{self.bucket}, suspicious folder: {self.suspicious_folder}")
    
    def move_video_to_suspicious(self, video_url: str) -> str:
        """
        Move video from events/ folder to suspicious/ folder
        
        Args:
            video_url: Full URL to the video file
            
        Returns:
            str: New URL to the moved video file
        """
        try:
            # Parse URL to extract object name
            # Example: http://localhost:9000/security-videos/events/video.mp4
            parsed = urlparse(video_url)
            object_name = parsed.path.lstrip('/')
            
            # Remove bucket name from path if present
            if object_name.startswith(f"{self.bucket}/"):
                object_name = object_name[len(self.bucket)+1:]
            
            # Skip if already in suspicious folder
            if object_name.startswith(f'{self.suspicious_folder}/'):
                logger.info(f"Video already in {self.suspicious_folder} folder: {object_name}")
                return video_url
            
            # Generate new object name in suspicious folder
            # events/video.mp4 -> suspicious/video.mp4 (or custom folder name)
            filename = object_name.split('/')[-1]
            new_object_name = f"{self.suspicious_folder}/{filename}"
            
            logger.info(f"Moving video: {object_name} -> {new_object_name}")
            
            # Copy object to new location
            self.client.copy_object(
                self.bucket,
                new_object_name,
                CopySource(self.bucket, object_name)
            )
            
            # Delete original object
            self.client.remove_object(self.bucket, object_name)
            
            # Generate new URL
            new_url = video_url.replace(object_name, new_object_name)
            
            logger.info(f"Video moved successfully: {new_url}")
            return new_url
            
        except S3Error as e:
            logger.error(f"MinIO error moving video: {e}", exc_info=True)
            return video_url  # Return original URL on error
        except Exception as e:
            logger.error(f"Error moving video: {e}", exc_info=True)
            return video_url  # Return original URL on error
    
    def check_bucket_exists(self) -> bool:
        """
        Check if the configured bucket exists
        
        Returns:
            bool: True if bucket exists
        """
        try:
            return self.client.bucket_exists(self.bucket)
        except Exception as e:
            logger.error(f"Error checking bucket existence: {e}")
            return False

