from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from celery import Celery
from celery.result import AsyncResult
from database import get_db
from models.camera import Camera
from models.schemas import (
    EmailResponse, 
    CameraUrlResponse, 
    TaskInfo, 
    TaskStatusResponse, 
    ActiveTasksResponse,
    TaskStopResponse,
    CameraStreamTask,
    BatchStartRequest,
    BatchStartResponse
)
from config.settings import settings
from typing import Dict, List, Any
from security.auth import require_jwt

router = APIRouter()

# Initialize Celery client
celery_app = Celery(
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend
)


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "master-service"}


@router.get("/camera/{camera_id}/email", response_model=EmailResponse)
async def get_email_by_camera_id(camera_id: str, db: Session = Depends(get_db), claims: Dict[str, Any] = Depends(require_jwt)):
    """Get email associated with a camera ID"""
    camera = db.query(Camera).filter(Camera.camera_id == camera_id).first()
    
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No email found for camera_id: {camera_id}"
        )
    
    return EmailResponse(camera_id=camera.camera_id, email=camera.email)


@router.get("/camera/{camera_id}/url", response_model=CameraUrlResponse)
async def get_camera_url_by_id(camera_id: str, db: Session = Depends(get_db), claims: Dict[str, Any] = Depends(require_jwt)):
    """Get camera URL (RTSP stream URL) by camera ID"""
    camera = db.query(Camera).filter(Camera.camera_id == camera_id).first()
    
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera not found: {camera_id}"
        )
    
    return CameraUrlResponse(
        camera_id=camera.camera_id, 
        camera_url=camera.camera_url,
        expected_fps=camera.expected_fps,
        record_fps=camera.record_fps,
        is_video=camera.is_video,
        buffersize=camera.buffersize,
        debug_enabled=camera.debug_enabled,
        debug_segment_duration=camera.debug_segment_duration,
        debug_minio_folder=camera.debug_minio_folder,
    )


@router.post("/camera/{camera_id}/start-stream", status_code=status.HTTP_202_ACCEPTED)
async def start_camera_stream(camera_id: str, db: Session = Depends(get_db), claims: Dict[str, Any] = Depends(require_jwt)):
    """
    Trigger Celery task to start processing camera stream
    
    Args:
        camera_id: Camera identifier
        
    Returns:
        Task information including task_id
    """
    # Verify camera exists
    camera = db.query(Camera).filter(Camera.camera_id == camera_id).first()
    
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera not found: {camera_id}"
        )
    
    if not camera.camera_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Camera {camera_id} has no URL configured"
        )
    
    # Trigger Celery task
    task = celery_app.send_task('tasks.start_process_camera_stream', args=[camera_id])
    
    return {
        'status': 'accepted',
        'camera_id': camera_id,
        'task_id': task.id,
        'message': f'Stream processing task started for camera {camera_id}'
    }


@router.post("/camera/batch-start-stream", response_model=BatchStartResponse, status_code=status.HTTP_202_ACCEPTED)
async def batch_start_camera_stream(
    request: BatchStartRequest, 
    db: Session = Depends(get_db), 
    claims: Dict[str, Any] = Depends(require_jwt)
):
    """
    Trigger Celery tasks to start processing multiple camera streams
    
    Args:
        request: BatchStartRequest containing list of camera_ids
        
    Returns:
        BatchStartResponse with mapping of camera_id to task_id
    """
    if not request.camera_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="camera_ids list cannot be empty"
        )
    
    # Verify all cameras exist and have URLs
    cameras = db.query(Camera).filter(Camera.camera_id.in_(request.camera_ids)).all()
    found_camera_ids = {camera.camera_id for camera in cameras}
    missing_cameras = set(request.camera_ids) - found_camera_ids
    
    if missing_cameras:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cameras not found: {', '.join(missing_cameras)}"
        )
    
    # Check for cameras without URLs
    cameras_without_url = [camera.camera_id for camera in cameras if not camera.camera_url]
    if cameras_without_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cameras without URL configured: {', '.join(cameras_without_url)}"
        )
    
    # Trigger Celery batch task asynchronously (don't wait for completion)
    task = celery_app.send_task('tasks.start_process_camera_stream_batch', args=[request.camera_ids])
    
    return BatchStartResponse(
        status='accepted',
        tasks={},  # Task IDs will be populated by the batch task asynchronously
        total_count=len(request.camera_ids),
        message=f'Batch stream processing started for {len(request.camera_ids)} cameras. Batch task ID: {task.id}'
    )


@router.get("/tasks/active", response_model=ActiveTasksResponse)
async def get_active_tasks(claims: Dict[str, Any] = Depends(require_jwt)):
    """
    Get all currently active camera stream tasks
    
    Returns:
        List of active camera stream tasks with task_id and camera_id
    """
    try:
        inspector = celery_app.control.inspect()
        active_tasks_dict = inspector.active()
        
        if not active_tasks_dict:
            return ActiveTasksResponse(
                active_tasks=[],
                total_count=0
            )
        
        # Filter only camera stream tasks and extract camera_id
        result: List[CameraStreamTask] = []
        
        for worker, tasks in active_tasks_dict.items():
            for task in tasks:
                task_name = task.get('name')
                # Filter only start_process_camera_stream tasks
                if task_name == 'tasks.start_process_camera_stream':
                    task_id = task.get('id')
                    args = task.get('args', [])
                    # Camera ID is the first argument
                    camera_id = args[0] if args and len(args) > 0 else 'unknown'
                    
                    result.append(CameraStreamTask(
                        task_id=task_id,
                        camera_id=camera_id
                    ))
        
        return ActiveTasksResponse(
            active_tasks=result,
            total_count=len(result)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get active tasks: {str(e)}"
        )


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str, claims: Dict[str, Any] = Depends(require_jwt)):
    """
    Get status of a specific task by ID
    
    Args:
        task_id: The Celery task ID
        
    Returns:
        Task status information
    """
    try:
        task_result = AsyncResult(task_id, app=celery_app)
        
        # Handle result safely to avoid serialization errors
        result = None
        if task_result.ready():
            # Check if result is an exception
            if isinstance(task_result.result, Exception):
                result = {
                    'error': str(task_result.result),
                    'error_type': type(task_result.result).__name__
                }
            else:
                result = task_result.result
        
        return TaskStatusResponse(
            task_id=task_id,
            status=task_result.status,
            result=result,
            traceback=task_result.traceback
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get task status: {str(e)}"
        )


@router.post("/tasks/{task_id}/stop", response_model=TaskStopResponse)
async def stop_task(task_id: str, claims: Dict[str, Any] = Depends(require_jwt)):
    """
    Stop a running task by revoking it
    
    Args:
        task_id: The Celery task ID to stop
        
    Returns:
        Status of the stop operation
    """
    try:
        # Check if task exists and is active
        inspector = celery_app.control.inspect()
        active_tasks_dict = inspector.active()
        
        task_found = False
        if active_tasks_dict:
            for worker, tasks in active_tasks_dict.items():
                if any(t.get('id') == task_id for t in tasks):
                    task_found = True
                    break
        
        if not task_found:
            # Check if task exists in backend
            task_result = AsyncResult(task_id, app=celery_app)
            if task_result.status == 'PENDING':
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Task {task_id} not found or not running"
                )
        
        # Revoke the task with terminate=True
        celery_app.control.revoke(task_id, terminate=True)
        
        return TaskStopResponse(
            status='success',
            task_id=task_id,
            message=f'Task {task_id} has been stopped'
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop task: {str(e)}"
        )
