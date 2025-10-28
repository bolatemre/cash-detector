"""
Celery tasks for camera stream processing

This module provides long-running tasks for processing camera streams:
- start_process_camera_stream: Starts infinite video processing with hand detection
- stop_process_camera_stream: Stops a running camera processing task

Usage:
    # Start processing
    result = start_process_camera_stream.apply_async(args=['camera-123'])
    task_id = result.id
    
    # Stop processing
    stop_process_camera_stream.apply_async(args=[task_id])
"""

import logging
import requests
from datetime import datetime
from celery_app import celery_app
from config.settings import settings
from services.camera_service import target_recording, CameraConnectionLostError

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True, 
    name='tasks.start_process_camera_stream',
    time_limit=None,  # No time limit - runs until stopped
    soft_time_limit=None,
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(CameraConnectionLostError, ConnectionError, requests.exceptions.RequestException),
    retry_kwargs={
        'max_retries': settings.celery_task_max_retries,
        'countdown': settings.celery_task_retry_backoff
    },
    retry_backoff=settings.celery_task_retry_backoff,
    retry_backoff_max=settings.celery_task_retry_backoff_max,
    retry_jitter=settings.celery_task_retry_jitter
)
def start_process_camera_stream(self, camera_id: str):
    logger.info(f"Starting camera stream processing for camera: {camera_id}")
    
    try:
        # Get camera URL from master-service
        api_url = f"{settings.master_service_url}/api/v1/camera/{camera_id}/url"
        logger.info(f"Fetching camera URL from: {api_url}")
        
        response = requests.get(api_url, timeout=5)
        
        if response.status_code == 404:
            error_msg = f"Camera {camera_id} not found in master-service"
            logger.error(error_msg)
            # Don't retry for 404 - camera doesn't exist
            raise Exception(f"Camera not found: {camera_id}")
        
        if response.status_code != 200:
            error_msg = f"Failed to get camera URL: HTTP {response.status_code}"
            logger.error(error_msg)
            # Retry for other HTTP errors (500, 503, etc.)
            raise requests.exceptions.RequestException(error_msg)
        
        data = response.json()
        camera_url = data.get('camera_url')
        expected_fps = data.get('expected_fps')
        record_fps = data.get('record_fps')
        
        logger.info(f"Camera URL for {camera_id}: {camera_url}")
        logger.info(f"Camera FPS settings - Expected: {expected_fps}, Record: {record_fps}")
        
        if not camera_url:
            error_msg = f"Camera {camera_id} has no URL configured"
            logger.error(error_msg)
            # Don't retry - configuration issue
            raise Exception(error_msg)
        
        # Start processing - target_recording will create the video capture internally
        try:
            # Callback to check if task was revoked
            def should_stop():
                revoked = celery_app.control.inspect().revoked()
                if revoked:
                    # revoked is a dict like {'worker_name': ['task_id1', 'task_id2']}
                    for worker_tasks in revoked.values():
                        if self.request.id in worker_tasks:
                            logger.info(f"Task {self.request.id} was revoked, stopping")
                            return True
                return False
            
            logger.info(f"Starting streaming for camera {camera_id}")
            logger.info(f"Task ID: {self.request.id} - Use celery.control.revoke('{self.request.id}', terminate=True) to stop")
            
            # This will run indefinitely until stopped or stream ends
            target_recording(
                camera_url, 
                camera_id=camera_id, 
                should_stop_callback=should_stop, 
                max_failed_reads=settings.camera_max_failed_reads,
                expected_fps=expected_fps,
                record_fps=record_fps
            )
            
            # If we reach here, it means the stream ended naturally or was stopped
            logger.info(f"Target recording finished for camera {camera_id}")
            return {
                'status': 'completed',
                'camera_id': camera_id,
                'camera_url': camera_url,
                'message': 'Camera stream processing completed (stream ended or stopped)',
                'timestamp': datetime.utcnow().isoformat()
            }
        except CameraConnectionLostError as e:
            # Camera connection was lost - this will trigger autoretry
            error_msg = f"Camera connection lost: {e}"
            logger.error(error_msg)
            retry_info = f"unlimited" if settings.celery_task_max_retries is None else settings.celery_task_max_retries
            logger.info(f"Task will be retried (attempt {self.request.retries + 1}/{retry_info})")
            # Re-raise to trigger autoretry
            raise
        except Exception as e:
            error_msg = f"Error during target recording: {e}"
            logger.error(error_msg, exc_info=True)
            # Re-raise to let Celery handle it
            raise
        
    except requests.exceptions.RequestException as e:
        error_msg = f"Error connecting to master-service: {e}"
        logger.error(error_msg)
        retry_info = f"unlimited" if settings.celery_task_max_retries is None else settings.celery_task_max_retries
        logger.info(f"Task will be retried (attempt {self.request.retries + 1}/{retry_info})")
        # Re-raise to trigger autoretry
        raise
    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        logger.error(error_msg, exc_info=True)
        # Don't retry for unexpected errors - might be a bug
        raise


@celery_app.task(name='tasks.stop_process_camera_stream')
def stop_process_camera_stream(task_id: str):
    """
    Stop processing camera stream by revoking the task
    
    Args:
        task_id: The Celery task ID to revoke
        
    Returns:
        dict: Status of the revoke operation
    """
    logger.info(f"Stopping camera stream processing task: {task_id}")
    
    try:
        # Revoke the task with terminate=True to force stop
        celery_app.control.revoke(task_id, terminate=True)
        
        logger.info(f"Successfully revoked task {task_id}")
        return {
            'status': 'success',
            'task_id': task_id,
            'message': 'Camera stream processing task stopped',
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        error_msg = f"Error stopping task {task_id}: {e}"
        logger.error(error_msg, exc_info=True)
        return {
            'status': 'error',
            'task_id': task_id,
            'error': error_msg
        }

