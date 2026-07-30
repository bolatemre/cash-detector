"""
MinIO Service for downloading videos for classification
"""

import os
import logging
import tempfile
from minio import Minio
from minio.error import S3Error
from config.settings import settings

logger = logging.getLogger(__name__)


class MinioService:
    """Service for downloading video files from MinIO for classification"""
    
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
        self.temp_dir = settings.temp_video_dir
        
        # Ensure temp directory exists
        os.makedirs(self.temp_dir, exist_ok=True)
        
        logger.info(f"MinIO service initialized: {endpoint}/{self.bucket}, temp dir: {self.temp_dir}")
    
    def download_video_to_temp(self, video_path: str, bucket_name: str | None = None) -> str:
        """
        Download video from MinIO to system temporary file
        
        Args:
            video_path: Path to video file in MinIO bucket
            
        Returns:
            str: Path to system temporary file, or None if download failed
        """
        try:
            # Generate temporary file using system temp directory
            filename = os.path.basename(video_path)
            file_extension = os.path.splitext(filename)[1]
            
            # Create temporary file with proper extension
            temp_file = tempfile.NamedTemporaryFile(
                suffix=file_extension,
                delete=False,
                dir=self.temp_dir
            )
            temp_file_path = temp_file.name
            temp_file.close()
            
            bucket = bucket_name or self.bucket
            logger.info(f"Downloading video from MinIO: {bucket}/{video_path}")
            
            # Download file from MinIO
            self.client.fget_object(
                bucket_name=bucket,
                object_name=video_path,
                file_path=temp_file_path
            )
            
            logger.info(f"Video downloaded successfully to: {temp_file_path}")
            return temp_file_path
            
        except S3Error as e:
            logger.error(f"MinIO S3 error while downloading {video_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error downloading video from MinIO: {e}", exc_info=True)
            return None
    
    def cleanup_temp_file(self, file_path: str) -> bool:
        """
        Clean up temporary file
        
        Args:
            file_path: Path to temporary file to delete
            
        Returns:
            bool: True if file was deleted successfully
        """
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Cleaned up temporary file: {file_path}")
                return True
            return True
        except Exception as e:
            logger.error(f"Error cleaning up temporary file {file_path}: {e}")
            return False
