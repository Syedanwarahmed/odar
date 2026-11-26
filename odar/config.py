from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="/etc/odar/odar.env", env_prefix="ODAR_", extra="ignore"
    )
    env: str = "lab"
    log_dir: str = "/var/log/odar"
    log_level: str = "INFO"
    read_only: bool = True
    db_dsn: Optional[str] = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
