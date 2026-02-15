import sys
import logging
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    STORAGE_TYPE: str
    ACCESS_KEY: str 
    SECRET_KEY: str
    S3_ENDPOINT: str
    BUCKET_NAME: str
    YOLO_MODEL_FILENAME: str
    OUTPUT_CSV_DIR: str  
    model_config = SettingsConfigDict(env_file=".env")


@lru_cache
def get_settings():
    return Settings()


def setup_logging():
    log_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):
        record = log_factory(*args, **kwargs)        
        return record

    logging.setLogRecordFactory(record_factory)

    log_format = (
        "%(asctime)s [%(levelname)s] "
        "%(name)s: %(funcName)s (%(lineno)d) '%(message)s'"
    )

    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)