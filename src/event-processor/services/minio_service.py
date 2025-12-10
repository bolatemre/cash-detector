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
        Move video from events/ folder to suspicious/ folder.
        If suspicious_folder is not set and video is in a different bucket, move it to settings.minio_bucket.
        
        Args:
            video_url: Full URL to the video file
            Example: http://localhost:9000/security-videos/events/video.mp4
            Example: http://localhost:9000/other-bucket/events/video.mp4
            
        Returns:
            str: New URL to the moved video file
        """
        try:
            # Parse URL to extract bucket and object name
            # Example: http://localhost:9000/security-videos/events/video.mp4
            parsed = urlparse(video_url)
            path_parts = parsed.path.lstrip('/').split('/', 1)
            
            # Extract source bucket and object name
            if len(path_parts) == 2:
                source_bucket = path_parts[0]
                object_name = path_parts[1]
            else:
                # If no bucket in path, assume it's in the configured bucket
                source_bucket = self.bucket
                object_name = path_parts[0] if path_parts else ''
            
            target_bucket = self.bucket
            
            # If suspicious_folder is not set
            if not self.suspicious_folder or not self.suspicious_folder.strip():
                # Only move if buckets are different
                if source_bucket != target_bucket:
                    # Move to target bucket keeping the same folder structure
                    new_object_name = object_name
                    logger.info(f"Moving video from bucket {source_bucket} to {target_bucket} (same folder): {object_name} -> {new_object_name}")
                else:
                    # Same bucket, no suspicious_folder - don't move
                    logger.info(f"Suspicious folder not set and same bucket, not moving: {object_name}")
                    return video_url
            else:
                # suspicious_folder is set - use original logic
                # Skip if already in suspicious folder
                if object_name.startswith(f'{self.suspicious_folder}/'):
                    logger.info(f"Video already in {self.suspicious_folder} folder: {object_name}")
                    return video_url
                
                # Generate new object name in suspicious folder
                # events/video.mp4 -> suspicious/video.mp4 (or custom folder name)
                filename = object_name.split('/')[-1]
                new_object_name = f"{self.suspicious_folder}/{filename}"
                
                # Check if we need to move between buckets
                if source_bucket != target_bucket:
                    logger.info(f"Moving video from bucket {source_bucket} to {target_bucket}: {object_name} -> {new_object_name}")
                else:
                    logger.info(f"Moving video within bucket {target_bucket}: {object_name} -> {new_object_name}")
            
            # Ensure target bucket exists
            if not self.client.bucket_exists(target_bucket):
                self.client.make_bucket(target_bucket)
                logger.info(f"Created target bucket: {target_bucket}")
            
            # Copy object to new location (supports cross-bucket copy)
            self.client.copy_object(
                target_bucket,
                new_object_name,
                CopySource(source_bucket, object_name)
            )
            
            # Delete original object from source bucket
            self.client.remove_object(source_bucket, object_name)
            
            # Generate new URL with target bucket
            # Replace the bucket and object name in the URL
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            new_url = f"{base_url}/{target_bucket}/{new_object_name}"
            
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

