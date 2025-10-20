from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from models.camera import Camera
from models.schemas import EmailResponse

router = APIRouter()


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

