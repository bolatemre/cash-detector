import logging
import os
import sys
from pathlib import Path

import torch
import numpy as np
import cv2

from deep_sort_realtime.deepsort_tracker import DeepSort

from config.settings import settings


def _add_yolov7_root_to_path() -> None:
    """YOLOv7 modules use `from utils.*`; their repo root must be on sys.path."""
    service_root = Path(__file__).resolve().parent
    for candidate in (
        service_root / "yolov7",
        service_root.parent / "yolov7",
    ):
        if (candidate / "utils").is_dir() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
            return


_add_yolov7_root_to_path()

from models.yolo import Model
from utils.datasets import letterbox
from utils.general import non_max_suppression, scale_coords

_SERVICE_DIR = os.path.dirname(os.path.abspath(__file__))


def setup_logging() -> None:
    log_format = (
        "%(asctime)s [%(levelname)s] "
        "%(name)s: %(funcName)s (%(lineno)d) '%(message)s'"
    )
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format=log_format,
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


setup_logging()
logger = logging.getLogger(__name__)


def _resolve_tracking_model_path() -> Path:
    """Absolute paths as-is; relative paths joined to repo root (same idea as classification run_yolo7)."""
    raw = settings.tracking_model_path
    if os.path.isabs(raw):
        return Path(os.path.abspath(os.path.expanduser(raw)))
    service_dir = Path(__file__).resolve().parent
    project_root = service_dir.parent.parent
    return Path(os.path.abspath(os.path.join(str(project_root), raw)))


MODEL_PATH = _resolve_tracking_model_path()


def make_model() -> Model:
    config_path = settings.yolov7_config_path
    model = Model(config_path).to(settings.yolov7_device)
    state = torch.load(MODEL_PATH, map_location=settings.yolov7_device)
    model.load_state_dict(state, strict=True)
    model.eval()
    model.names = settings.class_names   
    return model


def detect_objects(frame: np.ndarray, model: Model) -> np.ndarray:
    """
    Detects objects in the frame using the provided model.
    """
    img = letterbox(frame, settings.yolo_img_size, stride=32)[0]
    img = img[:, :, ::-1].transpose(2, 0, 1)  
    img = np.ascontiguousarray(img)
    img = torch.from_numpy(img).float().to(settings.yolov7_device)
    img /= 255.0
    img = img.unsqueeze(0)    
    with torch.no_grad():
        pred = model(img)[0]    
    pred = non_max_suppression(pred, settings.conf_threshold, settings.iou_threshold)    
    if pred[0] is None:
        return []        
    det = pred[0]
    det[:, :4] = scale_coords(img.shape[2:], det[:, :4], frame.shape).round()    
    # Remove very small banknotes detections
    banknote_mask = det[:, 5].cpu().numpy() == 0
    if np.any(banknote_mask):
        banknote_dets = det[banknote_mask]
        areas = (banknote_dets[:, 2] - banknote_dets[:, 0]) * (banknote_dets[:, 3] - banknote_dets[:, 1])
        min_area = settings.min_area
        valid_banknotes = banknote_dets[areas.cpu().numpy() >= min_area]        
        other_dets = det[~banknote_mask]
        if len(other_dets) > 0:
            det = torch.cat([valid_banknotes, other_dets])
        else:
            det = valid_banknotes    
    if len(det) > 0:
        logging.debug(f"Detected {len(det)} objects: {det[:, 5].cpu().numpy()}")    
    return det.cpu().numpy()


def is_inside(box_inner: tuple, box_outer: tuple) -> bool:
    """
    Checks if box_inner (x1, y1, x2, y2) is inside box_outer.
    """
    ix1, iy1, ix2, iy2 = box_inner
    ox1, oy1, ox2, oy2 = box_outer
    return ix1 >= ox1 and iy1 >= oy1 and ix2 <= ox2 and iy2 <= oy2


def update_home_zone(detections: list, home_zone: tuple | None) -> tuple | None:
    """ 
    Updates the home zone with the detected cash register position.
    """
    detected_x1 = None
    for det in detections:
        x1, y1, x2, y2, conf, cls = det
        if int(cls) == 1:
            detected_x1 = int(x1)
            if home_zone is None:
                home_zone = (int(x1), int(y1), int(x2), int(y2))
                logger.info("Initial home zone stored: %s", home_zone)
            break
    # Update ONLY left x-coordinate
    if home_zone is not None and detected_x1 is not None:
        old_x1, old_y1, old_x2, old_y2 = home_zone
        home_zone = (detected_x1, old_y1, old_x2, old_y2)
    return home_zone


def get_change_zone(frame_width: int) -> tuple:
    """
    Returns change zone as (x1, y1, x2, y2) - 1/3 from right by x coordinate.
    """
    change_zone_x = int(frame_width * 2/3)  # Start at 2/3 from left (1/3 from right)
    return (change_zone_x, 0, frame_width, None)  # y2 will be set based on frame height


def is_in_change_zone(bbox: tuple, change_zone: tuple) -> bool:
    """
    Check if bbox is in change zone.
    """
    x1, y1, x2, y2 = bbox
    cz_x1, cz_y1, cz_x2, cz_y2 = change_zone
    return x1 >= cz_x1


class BanknoteTracker:
    """
    Tracks banknote objects and manages their positions and statuses.
    """
    def __init__(self):
        self.tracks = {}  # track_id -> tracking info
        self.banknote_positions = {}  # track_id -> last known position
        self.position_threshold = settings.position_threshold  # pixels threshold for position matching
        self.id_remap = {}
        
    def merge_nearby_tracks(self, current_frame: np.ndarray) -> list[int]:
        """
        Merge tracks that are too close to each other to prevent duplication.
        """
        merged_ids = set()
        track_ids = list(self.tracks.keys())
        for i, track_id1 in enumerate(track_ids):
            if track_id1 in merged_ids or track_id1 not in self.tracks:
                continue
            pos1 = self.banknote_positions.get(track_id1)
            if pos1 is None:
                continue
            for track_id2 in track_ids[i + 1:]:
                if track_id2 in merged_ids or track_id2 not in self.tracks:
                    continue
                pos2 = self.banknote_positions.get(track_id2)
                if pos2 is None:
                    continue
                    # Calculate Euclidean distance
                dist = np.linalg.norm(np.array(pos1) - np.array(pos2))
                # Check if tracks are close enough and have similar behavior
                if dist < self.position_threshold:
                    track1 = self.tracks[track_id1]
                    track2 = self.tracks[track_id2]
                    # Use actual age, not numeric ID
                    if track1['first_seen'] <= track2['first_seen']:
                        older_id, newer_id = track_id1, track_id2
                    else:
                        older_id, newer_id = track_id2, track_id1
                    older_track = self.tracks[older_id]
                    newer_track = self.tracks[newer_id]
                    # Merge state
                    older_track['first_seen'] = min(
                        older_track['first_seen'],
                        newer_track['first_seen']
                    )
                    older_track['last_seen'] = max(
                        older_track['last_seen'],
                        newer_track['last_seen']
                    )
                    older_track['was_in_home_zone'] |= newer_track['was_in_home_zone']
                    older_track['was_in_change_zone'] |= newer_track['was_in_change_zone']
                    older_track['in_home_zone'] |= newer_track['in_home_zone']
                    older_track['in_change_zone'] |= newer_track['in_change_zone']
                    # Remap IDs
                    self.id_remap[newer_id] = older_id
                    # Remove duplicate
                    del self.tracks[newer_id]
                    self.banknote_positions.pop(newer_id, None)
                    merged_ids.add(newer_id)
                    logging.info(
                        f"Merged tracks {newer_id} into {older_id} "
                        f"at frame {current_frame}"
                    )
        return merged_ids
        

    def update_track(self, track_id: int, bbox: tuple[int, int, int, int], frame_count: int, home_zone: bool, change_zone: bool) -> None:
        """
        Update tracking information for a banknote.
        
        Args:
            track_id: Unique identifier for the track
            bbox: Bounding box coordinates (x1, y1, x2, y2)
            frame_count: Current frame number
            home_zone: Whether the banknote is in home zone
            change_zone: Whether the banknote is in change zone
        """
        """Update tracking information for a banknote"""
        while track_id in self.id_remap:
            track_id = self.id_remap[track_id]
        if track_id not in self.tracks:
            self.tracks[track_id] = {
                'first_seen': frame_count,
                'last_seen': frame_count,
                'in_home_zone': False,
                'in_change_zone': False,
                'was_in_home_zone': False,
                'was_in_change_zone': False,
                'violations': []
            }
        track = self.tracks[track_id]
        track['last_seen'] = frame_count
        # Store current position for merging logic
        center_x = (bbox[0] + bbox[2]) / 2
        center_y = (bbox[1] + bbox[3]) / 2
        self.banknote_positions[track_id] = (center_x, center_y)
        # Check current zones
        currently_in_home = home_zone is not None and is_inside(bbox, home_zone)
        currently_in_change = is_in_change_zone(bbox, change_zone)
        # Update zone states
        if currently_in_home:
            track['in_home_zone'] = True
            track['was_in_home_zone'] = True
        else:
            track['in_home_zone'] = False
        if currently_in_change:
            track['in_change_zone'] = True
            track['was_in_change_zone'] = True
        else:
            track['in_change_zone'] = False
    

    def classify_track(self, track_id: int, video_ended: bool = False) -> str:
        """Classify track based on the four scenarios"""
        while track_id in self.id_remap:
            track_id = self.id_remap[track_id]
        if track_id not in self.tracks:
            return "UNKNOWN"
        track = self.tracks[track_id]
        # Scenario 1: banknotes appears on video and put into cash register (home_zone) -> ok
        if track['was_in_home_zone'] and not video_ended:
            return "OK"
        # Scenario 2: banknotes are taken from cash register and taken away but not in change zone -> alert
        if track['was_in_home_zone'] and not track['in_home_zone'] and not track['was_in_change_zone'] and video_ended:
            return "ALERT"
        # Scenario 2: banknotes are taken from cash register and taken away but not in change zone -> alert
        if track['was_in_home_zone'] and not track['was_in_change_zone'] and video_ended:
            return "OK"
        # Scenario 3: banknotes are taken from cash register or they appear on video and go to change zone -> ok
        if track['was_in_change_zone']:
            return "OK"
        # Scenario 4: banknotes appears on video and do not come to cash register or change zone by the end of the video -> alert
        if video_ended and not track['was_in_home_zone'] and not track['was_in_change_zone']:
            return "ALERT"
        # Default case during tracking
        return "TRACKING"


def process_detections_for_tracker(detections: np.ndarray) -> list[tuple[list[int], float, int]]:
    """
    Convert detections to format expected by DeepSort tracker
    """
    raw_detections = []
    for det in detections:
        x1, y1, x2, y2, conf, cls = det
        w = max(0, x2 - x1)
        h = max(0, y2 - y1)
        raw_detections.append(([x1, y1, w, h], float(conf), int(cls)))
    return raw_detections


def generate_final_report(banknote_tracker: BanknoteTracker) -> tuple[int, int, str]:
    """
    Generate final classification report
    """
    logger.info("Final classification results:")
    alerts = 0
    oks = 0    
    for track_id in banknote_tracker.tracks:
        final_status = banknote_tracker.classify_track(track_id, video_ended=True)
        track_info = banknote_tracker.tracks[track_id]        
        logger.info(
            "Track %s: %s (Home: %s, Change: %s)",
            track_id,
            final_status,
            track_info["was_in_home_zone"],
            track_info["was_in_change_zone"],
        )
        if final_status == "ALERT":
            alerts += 1
        elif final_status == "OK":
            oks += 1    
    logger.info("Summary: %s OK, %s ALERTS", oks, alerts)
    final_status = "ALERT" if alerts > 0 else "ALL CLEAR"
    logger.info("Final status: %s", final_status)
    return oks, alerts, final_status


def object_by_zones(video_source: str | Path) -> dict:
    """
    Run tracking on a local video file path (caller downloads from MinIO when using Kafka payloads).
    """
    model = make_model()
    tracker = DeepSort(**settings.deepsort_config)
    banknote_tracker = BanknoteTracker()
    source = str(video_source)
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open tracking video source: {source}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    frame_interval = int(fps * settings.target_interval)
    frame_count = 0    
    # Persistent home zone
    home_zone = None
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    change_zone = get_change_zone(frame_width)   
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        frame_count += 1
        if frame_count % frame_interval != 0:
            continue            
        detections = detect_objects(frame, model)
        home_zone = update_home_zone(detections, home_zone)        
        raw_detections = process_detections_for_tracker(detections)
        tracks = tracker.update_tracks(raw_detections, frame=frame)
        for track in tracks:
            if not track.is_confirmed():
                continue                
            track_id = track.track_id
            cls = track.get_det_class()
            ltrb = track.to_ltrb()
            if cls == 0:  # Banknote
                banknote_tracker.update_track(track_id, ltrb, frame_count, home_zone, change_zone)        
        # Merge nearby tracks to prevent ID fragmentation
        merged_ids = banknote_tracker.merge_nearby_tracks(tracks)        
        if merged_ids:
            logging.info(f"Merged duplicate banknote tracks: {merged_ids}")
            
    # Final classification when video ends
    oks, alerts, final_status = generate_final_report(banknote_tracker)
    cap.release()
    return {
        "event_type": "suspicious" if final_status == "ALERT" else "cash_register",
        "final_status": final_status,
        "alerts": alerts,
        "oks": oks,
    }
