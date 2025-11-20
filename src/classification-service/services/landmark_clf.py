"""
Action Recognition Classifier using YOLO and MediaPipe Pose

ROI - area around body
MediaPipe pose detects poseLandmarks
When YOLO detect banknote near body (in hands), mediapipe tracks coordinates of shoulders, 
wrists, hips and other body landmarks to detect if banknote is placed into the pocket or not

Classification:
- class 1: pocket (suspicious action)
- class 0: cash_register (normal action)
"""
import cv2
import numpy as np
import logging
from typing import Tuple, List, Optional, Dict
from ultralytics import YOLO
import mediapipe as mp
from tensorflow.keras.models import load_model
from config.settings import settings

logger = logging.getLogger(__name__)

# Pose Setup
mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils

# Selected body landmarks for tracking
SELECTED_LANDMARKS = [
    mp_pose.PoseLandmark.LEFT_SHOULDER,
    mp_pose.PoseLandmark.RIGHT_SHOULDER,
    mp_pose.PoseLandmark.LEFT_ELBOW,
    mp_pose.PoseLandmark.RIGHT_ELBOW,
    mp_pose.PoseLandmark.LEFT_WRIST,
    mp_pose.PoseLandmark.RIGHT_WRIST,
    mp_pose.PoseLandmark.LEFT_PINKY,
    mp_pose.PoseLandmark.RIGHT_PINKY,
    mp_pose.PoseLandmark.LEFT_INDEX,
    mp_pose.PoseLandmark.RIGHT_INDEX,
    mp_pose.PoseLandmark.LEFT_THUMB,
    mp_pose.PoseLandmark.RIGHT_THUMB,
    mp_pose.PoseLandmark.LEFT_HIP,
    mp_pose.PoseLandmark.RIGHT_HIP,
    mp_pose.PoseLandmark.LEFT_KNEE,
    mp_pose.PoseLandmark.RIGHT_KNEE,
    mp_pose.PoseLandmark.LEFT_ANKLE,
    mp_pose.PoseLandmark.RIGHT_ANKLE,
    mp_pose.PoseLandmark.LEFT_HEEL,
    mp_pose.PoseLandmark.RIGHT_HEEL,
    mp_pose.PoseLandmark.LEFT_FOOT_INDEX,
    mp_pose.PoseLandmark.RIGHT_FOOT_INDEX,
]


class ActionClassifier:
    """
    Action Recognition Classifier for detecting suspicious actions
    
    Uses YOLO for banknote detection and MediaPipe Pose for body landmark tracking
    to classify actions as either:
    - 1: pocket (suspicious - money going into pocket)
    - 0: cash_register (normal - money going into register)
    """
    
    def __init__(self):
        """Initialize the classifier with models and configurations"""
        logger.info("Initializing ActionClassifier (required for service operation)")

        logger.info(
            "Classifier settings: "
            f"yolo_model_path={settings.yolo_model_path}, "
            f"action_model_path={settings.action_model_path}, "
            f"pose_min_detection_confidence={settings.pose_min_detection_confidence}, "
            f"pose_min_tracking_confidence={settings.pose_min_tracking_confidence}, "
            f"object_class_id={settings.object_class_id}, "
            f"conf_threshold={settings.conf_threshold}, "
            f"target_interval={settings.target_interval}, "
            f"sequence_length={settings.sequence_length}"
        )
        
        # Load YOLO model for banknote detection
        try:
            self.yolo = YOLO(settings.yolo_model_path)
            logger.info(f"YOLO model loaded successfully from {settings.yolo_model_path}")
        except Exception as e:
            logger.error(f"CRITICAL: Failed to load YOLO model from {settings.yolo_model_path}: {e}")
            logger.error("Service cannot start without YOLO model. Please ensure model file exists.")
            raise RuntimeError(f"Failed to initialize YOLO model: {e}") from e
        
        # Load action classification model
        try:
            self.action_model = load_model(settings.action_model_path, compile=False)
            logger.info(f"Action classification model loaded successfully from {settings.action_model_path}")
        except Exception as e:
            logger.error(f"CRITICAL: Failed to load action model from {settings.action_model_path}: {e}")
            logger.error("Service cannot start without action model. Please ensure model file exists.")
            raise RuntimeError(f"Failed to initialize action classification model: {e}") from e
        
        # Initialize MediaPipe Pose
        self.pose = mp_pose.Pose(
            min_detection_confidence=settings.pose_min_detection_confidence,
            min_tracking_confidence=settings.pose_min_tracking_confidence
        )
        
        # Configuration
        self.object_class_id = settings.object_class_id
        self.conf_threshold = settings.conf_threshold
        self.target_interval = settings.target_interval
        self.sequence_length = settings.sequence_length
        
        logger.info("ActionClassifier initialized successfully")
    
    def extract_keypoints(self, pose_results) -> np.ndarray:
        """
        Extract coordinates (x, y) of selected body landmarks
        
        Args:
            pose_results: MediaPipe pose results
            
        Returns:
            np.ndarray: Flattened array of landmark coordinates
        """
        if pose_results.pose_landmarks:
            lm = np.array([
                [
                    pose_results.pose_landmarks.landmark[landmark].x,
                    pose_results.pose_landmarks.landmark[landmark].y                
                ]
                for landmark in SELECTED_LANDMARKS
            ]).flatten()
        else:
            lm = np.zeros(len(SELECTED_LANDMARKS) * 2)
        return lm
    
    def detect_objects(self, frame: np.ndarray) -> List[Tuple]:
        """
        Run YOLO object detection and filter by confidence
        
        Args:
            frame: Input video frame
            
        Returns:
            List of detected objects (x1, y1, x2, y2, conf, cls)
        """
        results = self.yolo(frame, verbose=False)
        if len(results) == 0 or results[0].boxes is None:
            return []
        
        boxes = [(*box.xyxy[0].cpu().numpy(),
                float(box.conf[0]),
                int(box.cls[0]))
                for box in results[0].boxes
                if float(box.conf[0]) > self.conf_threshold]
        return boxes
    
    def compute_object_features(self, x1: float, y1: float, x2: float, y2: float, 
                                frame_shape: Tuple[int, int, int]) -> np.ndarray:
        """
        Normalize bounding box coordinates
        
        Args:
            x1, y1, x2, y2: Bounding box coordinates
            frame_shape: Shape of the frame (h, w, c)
            
        Returns:
            np.ndarray: Normalized object features [center_x, center_y, width, height]
        """
        h, w, _ = frame_shape
        object_x = ((x1 + x2) / 2) / w
        object_y = ((y1 + y2) / 2) / h
        object_w = (x2 - x1) / w
        object_h = (y2 - y1) / h
        return np.array([object_x, object_y, object_w, object_h])
    
    def predict_action(self, sequence: np.ndarray) -> Tuple[int, float]:
        """
        Predict action from a sequence of features
        
        Args:
            sequence: Sequence of feature vectors
            
        Returns:
            Tuple[int, float]: (predicted_class, confidence)
        """
        X = np.expand_dims(np.array(sequence), axis=0)
        prediction = self.action_model.predict(X, verbose=0)
        predicted_class = int(np.argmax(prediction))
        confidence = float(np.max(prediction))
        return predicted_class, confidence
    
    def classify_video(self, video_path: str) -> Dict[str, any]:
        """
        Classify a video file for suspicious actions
        
        Args:
            video_path: Path to the video file
            
        Returns:
            Dict containing:
                - predicted_class: int (0=normal, 1=suspicious)
                - confidence: float
                - class_name: str ('normal' or 'suspicious')
                - features_collected: int
        """
        logger.info(f"Starting video classification: {video_path}")
        
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.error(f"Failed to open video: {video_path}")
            return {
                'predicted_class': -1,
                'confidence': 0.0,
                'class_name': 'error',
                'features_collected': 0,
                'error': 'Failed to open video'
            }
        
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        frame_interval = int(fps * self.target_interval)
        frame_count = 0
        all_features = []
        
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                frame_count += 1
                if frame_count % frame_interval != 0:
                    continue
                
                # Object Detection
                boxes = self.detect_objects(frame)
                for box in boxes:
                    x1, y1, x2, y2, conf, cls = box
                    
                    if cls != self.object_class_id:
                        continue
                    
                    # Pose Estimation
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    pose_results = self.pose.process(rgb)
                    
                    if not pose_results.pose_landmarks:
                        continue
                    
                    # Extract and combine features
                    pose_features = self.extract_keypoints(pose_results)
                    object_features = self.compute_object_features(x1, y1, x2, y2, frame.shape)
                    features = np.concatenate([object_features, pose_features])
                    all_features.append(features)
        
        finally:
            cap.release()
        
        logger.info(f"Total feature frames collected: {len(all_features)}")
        
        if len(all_features) < 1:
            logger.warning("No valid pose/object features extracted from video")
            return {
                'predicted_class': 0,
                'confidence': 0.0,
                'class_name': 'normal',
                'features_collected': 0,
                'message': 'No banknotes detected in video'
            }
        
        # Convert to numpy array
        sequence = np.array(all_features)
        
        # Pad or truncate sequence to SEQUENCE_LENGTH
        seq_len = sequence.shape[0]
        feature_dim = sequence.shape[1]
        
        if seq_len < self.sequence_length:
            pad_size = self.sequence_length - seq_len
            padding = np.zeros((pad_size, feature_dim))
            sequence = np.vstack([sequence, padding])
            logger.debug(f"Padded sequence from {seq_len} to {self.sequence_length}")
        elif seq_len > self.sequence_length:
            sequence = sequence[:self.sequence_length, :]
            logger.debug(f"Truncated sequence from {seq_len} to {self.sequence_length}")
        
        # Predict action
        predicted_class, confidence = self.predict_action(sequence)
        class_name = "suspicious" if predicted_class == 1 else "normal"
        
        result = {
            'predicted_class': predicted_class,
            'confidence': confidence,
            'class_name': class_name,
            'features_collected': len(all_features)
        }
        
        logger.info(f"Classification result: {class_name} (class {predicted_class}) "
                   f"with confidence {confidence:.2f}")
        
        return result
    
    def __del__(self):
        """Cleanup resources"""
        if hasattr(self, 'pose'):
            self.pose.close()


