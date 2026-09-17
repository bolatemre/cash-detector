"""Banknote presence detector using a fine-tuned YOLOv7-tiny model."""
import logging
import math
import os
import sys

import cv2
import numpy as np
import torch

from config.model import ModelSettings

logger = logging.getLogger(__name__)

_DETECTION_DIR = os.path.dirname(os.path.abspath(__file__))
_SERVICE_DIR = os.path.dirname(_DETECTION_DIR)


def _add_yolov7_root_to_path() -> None:
    """YOLOv7 modules use `from utils.*`; their repo root must be on sys.path."""
    for candidate in (
        os.path.join(_SERVICE_DIR, "yolov7"),
        os.path.join(os.path.dirname(_SERVICE_DIR), "yolov7"),
        "/app/yolov7",
    ):
        if os.path.isdir(os.path.join(candidate, "utils")) and candidate not in sys.path:
            sys.path.insert(0, candidate)
            return


_add_yolov7_root_to_path()

from models.yolo import Model
from utils.datasets import letterbox
from utils.general import non_max_suppression, scale_coords


def resolve_path(path: str) -> str:
    """Return an absolute path, keeping absolute inputs and searching known roots for relative ones."""
    if os.path.isabs(path):
        return path
    src_root = os.path.dirname(_SERVICE_DIR)
    project_root = os.path.dirname(src_root)
    for base in (_SERVICE_DIR, src_root, project_root, "/app"):
        candidate = os.path.join(base, path)
        if os.path.exists(candidate):
            return os.path.abspath(candidate)
    return os.path.abspath(os.path.join(_SERVICE_DIR, path))


def _resolve_device(settings: ModelSettings) -> torch.device:
    """Return the requested torch device, selecting cuda when the setting is 'auto'."""
    requested = settings.yolov7_device.lower()
    if requested == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(requested)


class YOLOv7Model:
    """Loaded fine-tuned YOLOv7-tiny model with inference helpers."""

    def __init__(self, settings: ModelSettings) -> None:
        self._settings = settings
        self.device = _resolve_device(settings)
        config_path = resolve_path(settings.yolov7_config_path)
        model_path = resolve_path(settings.yolo_model_path)
        try:
            self.model = Model(config_path).to(self.device)
            state = torch.load(model_path, map_location=self.device)
            self.model.load_state_dict(state, strict=True)
            self.model.eval()
        except Exception as e:
            raise RuntimeError(f"Failed to initialize YOLOv7 model from {model_path}: {e}") from e
        logger.info("YOLOv7 model loaded from %s on %s", model_path, self.device)

    def detect(self, frame: np.ndarray) -> np.ndarray:
        """Run YOLOv7 on a single frame and return (N, 6) detections."""
        img = letterbox(frame, self._settings.yolo_img_size, stride=32)[0]
        img = img[:, :, ::-1].transpose(2, 0, 1)
        img = np.ascontiguousarray(img)
        img = torch.from_numpy(img).float().to(self.device)
        img /= 255.0
        img = img.unsqueeze(0)
        with torch.no_grad():
            pred = self.model(img)[0]
        pred = non_max_suppression(
            pred,
            self._settings.conf_threshold,
            self._settings.iou_threshold,
        )
        if pred[0] is None:
            return np.empty((0, 6), dtype=np.float32)
        det = pred[0]
        det[:, :4] = scale_coords(img.shape[2:], det[:, :4], frame.shape).round()
        return det.cpu().numpy()

    def any_banknote_in_video(self, video_path: str) -> bool:
        """Sample frames from a video and return True if a banknote (class 0) is detected."""
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open video: {video_path}")
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        if not math.isfinite(fps) or fps <= 0:
            logger.warning("Invalid FPS %s for %s, defaulting to 30", fps, video_path)
            fps = 30.0
        frame_interval = max(1, int(fps * self._settings.target_interval))
        decoded_frames = 0
        frames_scanned = 0
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                if decoded_frames % frame_interval == 0:
                    frames_scanned += 1
                    detections = self.detect(frame)
                    for *_, conf, cls in detections:
                        if int(cls) == self._settings.object_class_id and conf >= self._settings.conf_threshold:
                            return True
                decoded_frames += 1
        finally:
            cap.release()
        if frames_scanned == 0:
            logger.warning(
                "No frames scanned from %s (decoded=%s); treating as not_detected",
                video_path,
                decoded_frames,
            )
        return False
