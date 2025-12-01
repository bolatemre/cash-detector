import cv2
import time
import logging
from datetime import datetime
import mediapipe as mp
import os
import threading
import imageio

from .minio_service import upload_video_to_minio
from .utils import mask_camera_url
from config.settings import settings

logger = logging.getLogger(__name__)

mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils


def _get_rotation_angle(cap: cv2.VideoCapture) -> int:
    """Read rotation metadata (if any) from capture device."""
    orientation_prop = getattr(cv2, "CAP_PROP_ORIENTATION_META", None)
    if orientation_prop is None:
        return 0

    try:
        value = cap.get(orientation_prop)
    except Exception:
        return 0

    if value is None:
        return 0

    try:
        angle = int(value)
    except (TypeError, ValueError):
        return 0

    angle %= 360
    if angle in {0, 90, 180, 270}:
        return angle

    return 0


def _apply_rotation(frame, angle: int):
    """Rotate frame to compensate orientation metadata."""
    if angle == 90:
        return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    if angle == 180:
        return cv2.rotate(frame, cv2.ROTATE_180)
    if angle == 270:
        return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return frame


class CameraConnectionLostError(Exception):
    """Raised when camera connection is lost (too many consecutive failed frame reads)"""
    pass

def target_recording(camera_url, camera_id=None, expected_fps=25, record_fps=20, is_video=False):
    """
    Function that take video as input. When hands are detected, video recording is started until hands disappear + timeout seconds.
    Short videos with detected object are stored in defined directory.
    
    Args:
        camera_url: URL or path to the camera stream
        camera_id: Optional camera identifier for logging
        expected_fps: Expected FPS for processing
        record_fps: FPS for video recording
        is_video: Boolean indicating if camera_url is a video file (True) or stream (False)
    """

    max_failed_reads = settings.camera_max_failed_reads
    no_hand_timeout = settings.camera_no_hand_timeout
    
    # Configure MediaPipe for better performance
    hands = mp_hands.Hands(max_num_hands=2, min_detection_confidence=0.3, min_tracking_confidence=0.1)
    recording = False
    no_hand_start = None
    out = None
    current_video_file = None  # Track current recording file path
    current_recording_started_at = None  # Track ISO timestamp of recording start
    failed_reads_count = 0
    
    # FPS tracking variables
    frame_count = 0
    start_time = time.time()
    last_log_time = start_time
    
    # Create video capture object with optimized settings for streaming
    logger.info(f"Connecting to camera stream: {mask_camera_url(camera_url)}")
    cap = cv2.VideoCapture(camera_url, cv2.CAP_FFMPEG)
    
    # Configure video capture for RTSP/network streams
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize buffer to get latest frame
    cap.set(cv2.CAP_PROP_FPS, expected_fps)  # Set expected FPS from camera settings
    
    if not cap.isOpened():
        error_msg = f"Failed to open camera stream: {mask_camera_url(camera_url)}"
        logger.error(error_msg)
        raise ConnectionError(error_msg)

    rotation_angle = _get_rotation_angle(cap)
    if rotation_angle:
        logger.info(f"Camera {camera_id}: applying rotation correction of {rotation_angle} degrees for portrait video")
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                if is_video:
                    break
                failed_reads_count += 1
                logger.warning(f"Failed to read frame from camera {camera_id} (attempt {failed_reads_count}/{max_failed_reads})")
                
                if failed_reads_count >= max_failed_reads:
                    error_msg = f"Failed to read {max_failed_reads} consecutive frames from camera {camera_id}, connection lost"
                    logger.error(error_msg)
                    raise CameraConnectionLostError(error_msg)
                
                continue
            
            # Successfully read frame, reset counter
            failed_reads_count = 0

            # Normalize orientation if needed
            if rotation_angle:
                frame = _apply_rotation(frame, rotation_angle)
            
            # Track frame processing rate
            frame_count += 1
            current_time = time.time()
            elapsed_time = current_time - last_log_time
            
            # Log FPS at configurable interval
            if elapsed_time >= settings.camera_fps_log_interval:
                fps = frame_count / elapsed_time
                logger.debug(f"Camera {camera_id}: Processing at {fps:.2f} FPS (processed {frame_count} frames in {elapsed_time:.2f}s)")
                
                # Log warning if FPS is below threshold (possible worker blocking)
                if fps < settings.camera_fps_warning_threshold and frame_count > 0:
                    logger.warning(f"Camera {camera_id}: Very low FPS ({fps:.2f}) - possible worker blocking or network issues")
                
                frame_count = 0
                last_log_time = current_time

            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.process(rgb_frame)
            hands_detected = results.multi_hand_landmarks is not None

            if hands_detected:
                # Reset timeout countdown once hands are detected again
                no_hand_start = None

                if not recording:
                    output_dir = os.getenv('CAMERA_OUTPUT_DIR', '/app/output/trigger/test')
                    os.makedirs(output_dir, exist_ok=True)
                    current_video_file = f"{output_dir}/recording_{camera_id}_{int(time.time())}.mp4"
                    current_recording_started_at = datetime.utcnow().isoformat() + 'Z'
                    
                    # Configure video writer with compression settings
                    # CRF (Constant Rate Factor): 0-51, lower=better quality/larger file
                    # Preset: faster=larger file, slower=smaller file
                    out = imageio.get_writer(
                        current_video_file,
                        fps=record_fps,
                        codec=settings.video_codec,
                        pixelformat=settings.video_pixel_format,
                        ffmpeg_params=[
                            '-crf', str(settings.video_crf),
                            '-preset', settings.video_preset
                        ]
                    )
                    recording = True
                    logger.info(f"Recording started for camera {camera_id}: {current_video_file} "
                               f"(codec={settings.video_codec}, crf={settings.video_crf}, preset={settings.video_preset})")
            else:
                if recording:
                    if no_hand_start is None:
                        no_hand_start = time.time()
                    elif time.time() - no_hand_start > no_hand_timeout:
                        recording = False
                        out.close()
                        out = None
                        no_hand_start = None
                        logger.info(f"Recording stopped for camera {camera_id}: {current_video_file}")
                        
                        # Upload video to MinIO asynchronously (non-blocking)
                        if current_video_file:
                            upload_thread = threading.Thread(
                                target=upload_video_to_minio,
                                args=(current_video_file, camera_id, current_recording_started_at),
                                daemon=True
                            )
                            upload_thread.start()
                            logger.info(f"Started async upload for: {current_video_file}")
                            current_video_file = None
                            current_recording_started_at = None
            
            if recording and out:
                out.append_data(rgb_frame)
                
    finally:
        logger.info(f"Cleaning up resources for camera {camera_id}")
        
        # Close any active video recording
        if out:
            out.close()
            logger.info(f"Closed video writer for camera {camera_id}")
            
            # Upload unfinished video to MinIO if exists (synchronous in cleanup)
            if current_video_file and os.path.exists(current_video_file):
                logger.info(f"Uploading unfinished video to MinIO: {current_video_file}")
                # Use synchronous upload in finally block to ensure cleanup is complete
                minio_path = upload_video_to_minio(current_video_file, camera_id, current_recording_started_at)
                if minio_path:
                    logger.info(f"Unfinished video uploaded to MinIO: {minio_path}")
                current_recording_started_at = None
        
        cap.release()
        cv2.destroyAllWindows()