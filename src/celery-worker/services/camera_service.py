import cv2
import time
import logging
import mediapipe as mp
from confluent_kafka import Producer
import json
import os
import threading

from .minio_service import upload_video_to_minio

logger = logging.getLogger(__name__)

mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils


class CameraConnectionLostError(Exception):
    """Raised when camera connection is lost (too many consecutive failed frame reads)"""
    pass

def target_recording(cap, camera_id=None, should_stop_callback=None, max_failed_reads=30):
    """
    Function that take video as input. When hands are detected, video recording is started until hands disappear + 5 seconds.
    Short videos with detected object are stored in defined directory.
    
    Args:
        cap: cv2.VideoCapture object
        camera_id: Optional camera identifier for logging
        should_stop_callback: Optional callback function that returns True if processing should stop
        max_failed_reads: Maximum number of consecutive failed frame reads before stopping (default: 30)
    """
    hands = mp_hands.Hands(max_num_hands=2)
    recording = False
    no_hand_start = None
    out = None
    current_video_file = None  # Track current recording file path
    failed_reads_count = 0
    
    try:
        while True:
            # Check if we should stop processing
            if should_stop_callback and should_stop_callback():
                logger.info(f"Stop signal received for camera {camera_id}, stopping recording")
                break
            
            ret, frame = cap.read()
            if not ret:
                failed_reads_count += 1
                logger.warning(f"Failed to read frame from camera {camera_id} (attempt {failed_reads_count}/{max_failed_reads})")
                
                if failed_reads_count >= max_failed_reads:
                    error_msg = f"Failed to read {max_failed_reads} consecutive frames from camera {camera_id}, connection lost"
                    logger.error(error_msg)
                    raise CameraConnectionLostError(error_msg)
                
                # Small delay before retry
                time.sleep(0.1)
                continue
            
            # Successfully read frame, reset counter
            failed_reads_count = 0

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.process(rgb)
            hands_detected = results.multi_hand_landmarks is not None

            if hands_detected:
                for hand_landmarks in results.multi_hand_landmarks:
                    mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
                if not recording:
                    output_dir = os.getenv('CAMERA_OUTPUT_DIR', '/app/output/trigger/test')
                    os.makedirs(output_dir, exist_ok=True)
                    current_video_file = f"{output_dir}/recording_{camera_id}_{int(time.time())}.mp4"
                    out = cv2.VideoWriter(current_video_file, cv2.VideoWriter_fourcc(*'mp4v'), 30, (frame.shape[1], frame.shape[0]))
                    recording = True
                    logger.info(f"Recording started for camera {camera_id}: {current_video_file}")
                no_hand_start = None
            else:
                if recording:
                    if no_hand_start is None:
                        no_hand_start = time.time()
                    elif time.time() - no_hand_start > 5:
                        recording = False
                        out.release()
                        out = None
                        logger.info(f"Recording stopped for camera {camera_id}: {current_video_file}")
                        
                        # Upload video to MinIO asynchronously (non-blocking)
                        if current_video_file:
                            upload_thread = threading.Thread(
                                target=upload_video_to_minio,
                                args=(current_video_file, camera_id),
                                daemon=True
                            )
                            upload_thread.start()
                            logger.info(f"Started async upload for: {current_video_file}")
                            current_video_file = None
            
            if recording and out:
                out.write(frame)
                
    finally:
        logger.info(f"Cleaning up resources for camera {camera_id}")
        
        # Close any active video recording
        if out:
            out.release()
            logger.info(f"Released video writer for camera {camera_id}")
            
            # Upload unfinished video to MinIO if exists (synchronous in cleanup)
            if current_video_file and os.path.exists(current_video_file):
                logger.info(f"Uploading unfinished video to MinIO: {current_video_file}")
                # Use synchronous upload in finally block to ensure cleanup is complete
                minio_path = upload_video_to_minio(current_video_file, camera_id)
                if minio_path:
                    logger.info(f"Unfinished video uploaded to MinIO: {minio_path}")
        
        cap.release()
        cv2.destroyAllWindows()