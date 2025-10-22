from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from celery import Celery
from database import get_db
from models.camera import Camera
from models.schemas import EmailResponse, CameraUrlResponse
from config.settings import settings

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
async def get_email_by_camera_id(camera_id: str, db: Session = Depends(get_db)):
    """Get email associated with a camera ID"""
    camera = db.query(Camera).filter(Camera.camera_id == camera_id).first()
    
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No email found for camera_id: {camera_id}"
        )
    
    return EmailResponse(camera_id=camera.camera_id, email=camera.email)


@router.get("/camera/{camera_id}/url", response_model=CameraUrlResponse)
async def get_camera_url_by_id(camera_id: str, db: Session = Depends(get_db)):
    """Get camera URL (RTSP stream URL) by camera ID"""
    camera = db.query(Camera).filter(Camera.camera_id == camera_id).first()
    
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera not found: {camera_id}"
        )
    
    return CameraUrlResponse(camera_id=camera.camera_id, camera_url=camera.camera_url)


@router.post("/camera/{camera_id}/start-stream", status_code=status.HTTP_202_ACCEPTED)
async def start_camera_stream(camera_id: str, db: Session = Depends(get_db)):
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

