import os
import time
import logging
from minio import Minio
from minio.error import S3Error
from .kafka_producer import send_video_uploaded_event

logger = logging.getLogger(__name__)


def get_minio_client():
    """
    Create and return a new MinIO client instance
    
    Returns:
        Minio: New MinIO client instance
    """
    logger.debug("Creating new MinIO client")
    client = Minio(
        endpoint=os.getenv('MINIO_ENDPOINT'),
        access_key=os.getenv('MINIO_ACCESS_KEY'),
        secret_key=os.getenv('MINIO_SECRET_KEY'),
        secure=os.getenv('MINIO_SECURE').lower() == "true"
    )
    return client


def upload_video_to_minio(
    local_file_path,
    camera_id,
    recording_started_at=None,
    object_subdir=None,
    send_event=True,
):
    """
    Upload video file to MinIO and delete local file
    
    Args:
        local_file_path: Path to local video file
        camera_id: Camera identifier for organizing files
        
    Returns:
        str: MinIO object path if successful, None otherwise
    """
    try:
        client = get_minio_client()
        bucket_name = os.getenv('MINIO_BUCKET')
        
        # Ensure bucket exists
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)
            logger.info(f"Created MinIO bucket: {bucket_name}")
        
        # Generate object name: camera_id/year/month/day[/subdir]/filename
        timestamp = time.localtime()
        filename = os.path.basename(local_file_path)
        object_prefix = f"{camera_id}/{timestamp.tm_year}/{timestamp.tm_mon:02d}/{timestamp.tm_mday:02d}"
        if object_subdir:
            safe_subdir = object_subdir.strip("/")
            object_name = f"{object_prefix}/{safe_subdir}/{filename}"
        else:
            object_name = f"{object_prefix}/{filename}"
        
        # Upload file
        logger.info(f"Uploading {local_file_path} to MinIO: {bucket_name}/{object_name}")
        client.fput_object(
            bucket_name=bucket_name,
            object_name=object_name,
            file_path=local_file_path,
            content_type='video/mp4'
        )
        
        logger.info(f"Successfully uploaded video to MinIO: {object_name}")
        
        # Send event to Kafka for regular event-driven processing
        if send_event:
            send_video_uploaded_event(
                camera_id=camera_id,
                video_path=object_name,
                bucket_name=bucket_name,
                recording_started_at=recording_started_at
            )
        
        # Delete local file after successful upload
        try:
            os.remove(local_file_path)
            logger.info(f"Deleted local file: {local_file_path}")
        except Exception as e:
            logger.warning(f"Failed to delete local file {local_file_path}: {e}")
        
        return object_name
        
    except S3Error as e:
        logger.error(f"MinIO S3 error while uploading {local_file_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error uploading video to MinIO: {e}", exc_info=True)
        return None

