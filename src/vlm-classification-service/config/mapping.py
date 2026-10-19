from pydantic_settings import BaseSettings

from config.prompts import DEFAULT_SYSTEM_PROMPT, DEFAULT_USER_PROMPT


class MappingSettings(BaseSettings):
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    user_prompt: str = DEFAULT_USER_PROMPT

    suspicious_event_type: str = "suspicious"
    normal_event_type: str = "normal"
    unknown_event_type: str = "unknown"
