"""
MediaPipe pose detect poseLandmarks
When YOLO detect banknote near body, mediapipe should track and write coordinates of shoulders, whirsts and hips to detect if banknote is placed into the pocket or on the table
"""
import csv
import time
from pathlib import Path

import mediapipe as mp
import cv2
import numpy as np
import pandas as pd
import torch
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError, EndpointConnectionError
import logging

from keypoints_config import get_settings, setup_logging
from models.yolo import Model
from utils.datasets import letterbox
from utils.general import non_max_suppression, scale_coords


SETTINGS = get_settings()
setup_logging()

BASE_DIR = Path(__file__).resolve().parents[5]
MODEL_PATH = BASE_DIR / "data" / "trained_models" / SETTINGS.YOLO_MODEL_FILENAME
OUTPUT_PATH = BASE_DIR / "data" / "processed" / "classification" / SETTINGS.OUTPUT_CSV_DIR
YOLO_FILES_TO_TRAIN = "yolo_files_to_train.csv"
OBJECT_CLASS_ID = 0
CONF_THRESHOLD = 0.5
IOU_THRESHOLD = 0.45
TARGET_INTERVAL = 0.1 
YOLO_IMG_SIZE = 640
DEVICE = 'cpu'
CLASS_NAMES = ["banknote", "cash register"]
POSE_COLUMNS = [
    "left_shoulder", "right_shoulder",
    "left_elbow", "right_elbow",
    "left_wrist", "right_wrist",
    "left_pinky", "right_pinky",
    "left_index", "right_index",
    "left_thumb", "right_thumb",
    "left_hip", "right_hip",
    "left_knee", "right_knee",
    "left_ankle", "right_ankle",
    "left_heel", "right_heel",
    "left_foot_index", "right_foot_index"
]

S3 = boto3.client(
    's3',
    endpoint_url = SETTINGS.S3_ENDPOINT,
    aws_access_key_id = SETTINGS.ACCESS_KEY,
    aws_secret_access_key = SETTINGS.SECRET_KEY, 
    config=Config(signature_version='s3v4')
)


def get_s3_folders() -> list:
    try:   
        response = S3.list_objects_v2(Bucket=SETTINGS.BUCKET_NAME, Delimiter='/')
        folders = [prefix['Prefix'] for prefix in response.get('CommonPrefixes', [])]
        logging.info(folders)
        return folders
    except EndpointConnectionError:
        logging.error("Can't connect to the S3.")
        return []
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '403':
            logging.error("Invalid Credentials (Access Key/Secret Key).")
        elif error_code == '404':
            logging.error("The bucket does not exist.")
        else:
            logging.error(f"S3 Error: {e}")
        return []
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        return []


def make_retrain_config_file(dirs: list) -> bool:
    try:
        OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
        file_path = OUTPUT_PATH / YOLO_FILES_TO_TRAIN        
        existing_combinations = set()
        all_rows = []
        if file_path.exists():
            with open(file_path, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    existing_combinations.add((row['folder_name'], row['filename']))
            counter = len(existing_combinations) + 1
        else:
            counter = 1
        for folder_name in dirs:
            display_folder = folder_name.strip("/")
            paginator = S3.get_paginator('list_objects_v2')            
            for page in paginator.paginate(Bucket=SETTINGS.BUCKET_NAME, Prefix=folder_name):
                for obj in page.get('Contents', []):
                    filename = obj['Key'].split('/')[-1] 
                    if not filename or (display_folder, filename) in existing_combinations:
                        continue                    
                    all_rows.append({
                        "id": counter,
                        "folder_name": display_folder,
                        "filename": filename,
                        "is_for_train": "", 
                        "checked_at": ""    
                    })
                    counter += 1
        headers = ["id", "folder_name", "filename", "is_for_train", "checked_at"]        
        if not all_rows:
            logging.info("No new files found to add.")
            return True
        file_mode = 'a' if file_path.exists() else 'w'        
        with open(file_path, mode=file_mode, newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            if file_mode == 'w':
                writer.writeheader()
            writer.writerows(all_rows)            
        logging.info(f"Added {len(all_rows)} new entries to {YOLO_FILES_TO_TRAIN}.")
        return True
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        return False


def get_presigned_url(file_key: str, expiration: int = 3600) -> str | None:
    try:
        response = S3.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': SETTINGS.BUCKET_NAME, 
                'Key': file_key
            },
            ExpiresIn=expiration
        )
        return response
    except ClientError as e:
        logging.error(f"Could not generate presigned URL for {file_key}: {e}")
        return None


def make_model() -> Model:    
    model = Model('cfg/training/yolov7_tiny_2cl.yaml').to(DEVICE)
    state = torch.load(MODEL_PATH, map_location=DEVICE)
    model.load_state_dict(state, strict=True)
    model.eval()
    model.names = CLASS_NAMES   
    return model


def detect_objects(frame, model) -> list[tuple]:   
    """Returns: list of tuples -> (x1, y1, x2, y2, conf, cls)"""
    img = letterbox(frame, YOLO_IMG_SIZE, stride=32)[0]
    img = img[:, :, ::-1].transpose(2, 0, 1)  
    img = np.ascontiguousarray(img)
    img = torch.from_numpy(img).float().to(DEVICE)
    img /= 255.0
    img = img.unsqueeze(0)
    with torch.no_grad():
        pred = model(img)[0]
    pred = non_max_suppression(pred, CONF_THRESHOLD, IOU_THRESHOLD)    
    if pred[0] is None:
        return []
    det = pred[0]
    det[:, :4] = scale_coords(img.shape[2:], det[:, :4], frame.shape).round()    
    results = []
    for *xyxy, conf, cls in det.cpu().numpy():
        results.append((xyxy[0], xyxy[1], xyxy[2], xyxy[3], float(conf), int(cls)))
    return results


def track_keypoints(stream_url, model):
    mp_pose = mp.solutions.pose
    pose = mp_pose.Pose(min_detection_confidence=0.4, min_tracking_confidence=0.2)
    mp_draw = mp.solutions.drawing_utils
    cap = cv2.VideoCapture(stream_url)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    frame_interval = int(fps * TARGET_INTERVAL)
    frame_count = 0
    logging.info("Starting detection... Press 'q' to quit.")
    all_rows = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_count += 1
        if frame_count % frame_interval != 0:
            continue
        h, w, _ = frame.shape
        detections = detect_objects(frame, model)
        logging.info(f"Detected classes: {[d[5] for d in detections]}")
        objects = [d for d in detections if d[5] == OBJECT_CLASS_ID]
        if len(objects) == 0:
            continue
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pose_result = pose.process(rgb)
        if not pose_result.pose_landmarks:
            continue
        lm = pose_result.pose_landmarks.landmark
        def kp(name):
            idx = mp_pose.PoseLandmark[name].value
            return (lm[idx].x, lm[idx].y)
        keypoints = {kp_name: kp(kp_name.upper()) for kp_name in POSE_COLUMNS}
        # Draw skeleton
        mp_draw.draw_landmarks(
            frame,
            pose_result.pose_landmarks,
            mp_pose.POSE_CONNECTIONS,
            mp_draw.DrawingSpec(color=(0, 165, 255), thickness=2, circle_radius=2),
            mp_draw.DrawingSpec(color=(120, 120, 120), thickness=2, circle_radius=2)
        )
        for (x1, y1, x2, y2, conf, cls) in objects:
            # normalized object values
            obj_x = ((x1 + x2) / 2) / w
            obj_y = ((y1 + y2) / 2) / h
            obj_w = (x2 - x1) / w
            obj_h = (y2 - y1) / h            
            row = {
                "timestamp": time.time(),
                "object_x": obj_x,
                "object_y": obj_y,
                "object_w": obj_w,
                "object_h": obj_h
            }
            for name in POSE_COLUMNS:
                kp_data = keypoints.get(name, (0, 0))
                row[f"{name}_x"] = kp_data[0]
                row[f"{name}_y"] = kp_data[1]
            all_rows.append(row)
            label = f"{model.names[cls]} {conf:.2f}"
            cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)),
                        (0, 0, 255), 2)
            cv2.putText(frame, label, (int(x1), int(y1) -8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (0, 0, 255), 2)
        cv2.imshow("Object + Pose Tracking", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    cap.release()
    cv2.destroyAllWindows()
    return all_rows


def make_choice():
    while True:
        choice = input("Press y (write True), n (write False), or q (Quit withought saving): ").strip().lower()
        if choice in ("y", "n", "q"):
            break
        print("Invalid input. Enter y, n, or q.")
    if choice == "q":
        print("Quitting loop.")
        return None
    if choice == "n":
        print(f"Write False.")
        return "n"
    return "y"


def write_keypoints_to_csv(all_rows: list, foldername: str, filename: str):
    clean_filename = Path(filename).stem
    csv_name = f"{foldername}_{clean_filename}.csv"
    file_path = OUTPUT_PATH / csv_name
    file_path.parent.mkdir(parents=True, exist_ok=True)
    headers = ["timestamp", "object_x", "object_y", "object_w", "object_h"] +\
        [kp + suffix for kp in POSE_COLUMNS for suffix in ["_x", "_y"]]        
    with open(file_path, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(all_rows)


def make_object_keypoints():
    file_to_train_path = OUTPUT_PATH / YOLO_FILES_TO_TRAIN
    if not file_to_train_path.exists():
        logging.warning(f"File {YOLO_FILES_TO_TRAIN} not found.")
        return False
    model = make_model()
    try:
        df = pd.read_csv(file_to_train_path)
        pending_indices = df[df['is_for_train'].isna()].index
        for idx in pending_indices:
            folder = df.at[idx, 'folder_name']
            filename = df.at[idx, 'filename']            
            file_key = f"{folder}/{filename}"
            stream_url = get_presigned_url(file_key)
            keypoints = track_keypoints(stream_url, model)
            choice = make_choice()
            if choice in ['y', 'n']:
                is_train = (choice == 'y')
                df.at[idx, 'is_for_train'] = (choice == 'y')
                df.at[idx, 'checked_at'] = pd.Timestamp.now()                
                df.to_csv(file_to_train_path, index=False)
                if is_train: 
                    write_keypoints_to_csv(keypoints, folder, filename)
    except Exception as e:
        logging.error(f"Error reading CSV: {e}")


if __name__ == '__main__':
    dirs = get_s3_folders()
    config_file = make_retrain_config_file(dirs)
    if config_file:
        make_object_keypoints()
