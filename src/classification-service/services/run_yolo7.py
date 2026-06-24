"""
Action Recognition Classifier using YOLOv7 and MediaPipe Pose

ROI - area around body
MediaPipe pose detects poseLandmarks
When YOLO detects a banknote near body (in hands), MediaPipe tracks coordinates of shoulders,
wrists, hips and other body landmarks to classify the action.

Classification:
- class 0: cash_register (normal action)
- class 1: alert (suspicious action)
- class 2: change (normal action)
"""
import torch
import sys
import os
import cv2
import numpy as np
import logging
from typing import Tuple, List, Optional, Dict


def _add_yolov7_root_to_path() -> None:
    """YOLOv7 modules use `from utils.*`; their repo root must be on sys.path."""
    service_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for candidate in (
        os.path.join(service_root, "yolov7"),
        os.path.join(os.path.dirname(service_root), "yolov7"),
    ):
        if os.path.isdir(os.path.join(candidate, "utils")) and candidate not in sys.path:
            sys.path.insert(0, candidate)
            return


_add_yolov7_root_to_path()

from utils.general import non_max_suppression, scale_coords
from utils.datasets import letterbox
from models.yolo import Model

import mediapipe as mp
from config.settings import settings

import tensorflow as tf

if settings.tensorflow_device.lower() == "cpu":
    tf.config.set_visible_devices([], "GPU")

from tensorflow.keras.models import load_model

_SERVICE_DIR = os.path.dirname(os.path.dirname(__file__))

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
]


class YOLOv7ActionClassifier:
    """
    Action Recognition Classifier for detecting suspicious actions using YOLOv7
    
    Uses custom YOLOv7 for banknote detection and MediaPipe Pose for body landmark tracking
    to classify actions into one of:
    - 0: cash_register (normal - money going into register)
    - 1: suspicious (suspicious - anomaly detected)
    - 2: change (normal - change given)
    """
    ACTION_CLASS_NAMES = {
        0: "cash_register",
        1: "suspicious",
        2: "change",
    }
    
    def __init__(self):
        """Initialize the classifier with models and configurations"""
        logger.info("Initializing YOLOv7ActionClassifier (required for service operation)")

        logger.info(
            "Classifier settings: "
            f"yolov7_config_path={settings.yolov7_config_path}, "
            f"yolo_model_path={settings.yolo_model_path}, "
            f"action_model_path={settings.action_model_path}, "
            f"pose_min_detection_confidence={settings.pose_min_detection_confidence}, "
            f"pose_min_tracking_confidence={settings.pose_min_tracking_confidence}, "
            f"object_class_id={settings.object_class_id}, "
            f"conf_threshold={settings.conf_threshold}, "
            f"target_interval={settings.target_interval}, "
            f"process_all_frames={settings.process_all_frames}, "
            f"sequence_length={settings.sequence_length}, "
            f"features_min_threshold={settings.features_min_threshold}, "
            f"yolov7_device={settings.yolov7_device}, "
            f"tensorflow_device={settings.tensorflow_device}"
        )
        
        # Load YOLOv7 model for banknote detection
        try:
            self.device = settings.yolov7_device
            config_path = settings.yolov7_config_path
            
            self.yolo_model = Model(config_path).to(self.device)
            
            # Build absolute path for state file (relative to project root)
            project_root = os.path.dirname(os.path.dirname(_SERVICE_DIR))  # project root
            state_path = os.path.abspath(os.path.join(project_root, settings.yolo_model_path))
            
            state = torch.load(state_path, map_location=self.device)
            self.yolo_model.load_state_dict(state, strict=True)
            self.yolo_model.eval()
            logger.info(f"YOLOv7 model loaded successfully from {state_path}")
        except Exception as e:
            logger.error(f"CRITICAL: Failed to load YOLOv7 model: {e}")
            logger.error("Service cannot start without YOLOv7 model. Please ensure model files exist.")
            raise RuntimeError(f"Failed to initialize YOLOv7 model: {e}") from e
        
        # Load action classification model
        try:
            # Handle both absolute and relative paths
            if os.path.isabs(settings.action_model_path):
                action_model_path = settings.action_model_path
            else:
                # If relative, assume it's relative to project root
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))  # project root
                action_model_path = os.path.abspath(os.path.join(project_root, settings.action_model_path))
            
            self.action_model = load_model(action_model_path, compile=False)
            logger.info(f"Action classification model loaded successfully from {action_model_path}")
        except Exception as e:
            logger.error(f"CRITICAL: Failed to load action model from {action_model_path}: {e}")
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
        self.features_threshold = settings.features_min_threshold

        logger.info("YOLOv7ActionClassifier initialized successfully")
    
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
        Run YOLOv7 object detection and return bounding boxes
        
        Args:
            frame: Input video frame
            
        Returns:
            List of detected objects (x1, y1, x2, y2, conf, cls)
        """
        img = letterbox(frame, 640, stride=32)[0]
        img = img[:, :, ::-1].transpose(2, 0, 1)
        img = np.ascontiguousarray(img)
        img = torch.from_numpy(img).float().to(self.device)
        img /= 255.0
        img = img.unsqueeze(0)
        with torch.no_grad():
            pred = self.yolo_model(img)[0]
        pred = non_max_suppression(pred, self.conf_threshold, 0.45)

        if pred[0] is None:
            return []
        det = pred[0]
        det[:, :4] = scale_coords(img.shape[2:], det[:, :4], frame.shape).round()

        results = []
        for *xyxy, conf, cls in det.cpu().numpy():
            results.append((xyxy[0], xyxy[1], xyxy[2], xyxy[3], float(conf), int(cls)))
        return results
    
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
                - predicted_class: int (0=cash_register, 1=suspicious, 2=change)
                - confidence: float
                - class_name: str ('cash_register' | 'suspicious' | 'change')
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
                if not settings.process_all_frames and frame_count % frame_interval != 0:
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
        
        if len(all_features) < self.features_threshold:
            logger.warning(
                "Insufficient pose/object features extracted from video "
                f"({len(all_features)} < {self.features_threshold})"
            )
            return {
                'predicted_class': 0,
                'confidence': 0.0,
                'class_name': "unknown",
                'features_collected': len(all_features),
                'message': 'Insufficient features collected for classification'
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
        class_name = self.ACTION_CLASS_NAMES.get(predicted_class, "unknown")
        
        # If classification is alert but confidence is below threshold, treat as cash_register
        if predicted_class == 1 and confidence < settings.classification_confidence_threshold:
            logger.info(
                f"Alert classification with low confidence ({confidence:.2f} < {settings.classification_confidence_threshold}), "
                f"treating as cash_register (features: {len(all_features)})"
            )
            predicted_class = 0
            class_name = self.ACTION_CLASS_NAMES[0]
        
        result = {
            'predicted_class': predicted_class,
            'confidence': confidence,
            'class_name': class_name,
            'features_collected': len(all_features)
        }
        
        logger.info(
            f"Classification result: {class_name} (class {predicted_class}) "
            f"with confidence {confidence:.2f}"
        )
        
        return result
    
    def __del__(self):
        """Cleanup resources"""
        if hasattr(self, 'pose'):
            self.pose.close()

