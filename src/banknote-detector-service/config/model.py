from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelSettings(BaseSettings):
    model_config = SettingsConfigDict(protected_namespaces=())

    yolo_model_path: str = "models_ft/12_03_2_state.pt"
    yolov7_config_path: str = "yolov7/cfg/training/yolov7_tiny_2cl.yaml"
    yolov7_device: str = "auto"  # "auto" uses cuda when available, otherwise cpu
    object_class_id: int = 0  # banknote
    conf_threshold: float = 0.25
    iou_threshold: float = 0.45
    yolo_img_size: int = 640
    target_interval: float = 0.1
