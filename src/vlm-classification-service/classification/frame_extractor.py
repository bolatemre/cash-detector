import logging

import cv2
from PIL import Image

from config.model import ModelSettings

logger = logging.getLogger(__name__)


class FrameExtractor:
    """Sample and resize frames from a local video file."""

    def __init__(self, settings: ModelSettings):
        self._settings = settings

    def extract(self, video_path: str) -> tuple[list[Image.Image], float]:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open video: {video_path}")

        try:
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps <= 0:
                raise RuntimeError("Failed to determine video FPS")

            duration = total_frames / fps
            num_frames = int(duration * self._settings.target_extract_fps)
            num_frames = max(2, min(num_frames, self._settings.max_allowed_frames, total_frames))

            logger.info(
                "Video info\n"
                "fps=%.2f\n"
                "total_frames=%s\n"
                "duration=%.2fs\n"
                "extracting=%s",
                fps,
                total_frames,
                duration,
                num_frames,
            )

            indices = [
                int(i * (total_frames - 1) / (num_frames - 1))
                for i in range(num_frames)
            ]
            target_set = set(indices)
            frames: list[Image.Image] = []
            current_index = 0

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if current_index in target_set:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    h, w = frame_rgb.shape[:2]
                    if max(w, h) > self._settings.max_image_size:
                        scale = self._settings.max_image_size / max(w, h)
                        new_w = max(1, int(w * scale))
                        new_h = max(1, int(h * scale))
                        frame_rgb = cv2.resize(
                            frame_rgb,
                            (new_w, new_h),
                            interpolation=cv2.INTER_AREA,
                        )
                    frames.append(Image.fromarray(frame_rgb))

                current_index += 1
                if current_index >= total_frames:
                    break

            if len(frames) < 2:
                raise RuntimeError(f"Failed to extract enough frames: {video_path}")

            effective_fps = (
                (len(frames) - 1) / duration
                if len(frames) > 1 and duration > 0
                else 1.0
            )
            logger.info("Extracted %s frames into memory", len(frames))
            return frames, effective_fps
        finally:
            cap.release()
