import json
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelSettings(BaseSettings):
    model_config = SettingsConfigDict(protected_namespaces=())

    model_name: str = "Qwen/Qwen3-VL-8B-Instruct-FP8"
    model_processor: str = "Qwen/Qwen3-VL-8B-Instruct-FP8"
    dtype: str = "auto"
    device_map: str = "auto"
    max_memory: dict[str, str] = {
        0: "2GiB",
        "cpu": "14GiB"
    }

    max_new_tokens: int = 1024
    do_sample: bool = False
    temperature: float = 0.1
    top_p: float = 1.0
    top_k: int = 0
    repetition_penalty: float = 1.0

    target_extract_fps: float = 10.0
    max_allowed_frames: int = 256
    max_image_size: int = 576

    max_retries: int = 2
    retry_delay_seconds: int = 10

    @field_validator("max_memory", mode="before")
    @classmethod
    def parse_max_memory(cls, value: Any) -> dict[str, str]:
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, dict):
            raise ValueError("MAX_MEMORY must be a JSON object")
        return {str(key): str(item) for key, item in value.items()}

    def parsed_max_memory(self) -> dict[int | str, str]:
        parsed: dict[int | str, str] = {}
        for key, value in self.max_memory.items():
            parsed[int(key) if key.isdigit() else key] = value
        return parsed
