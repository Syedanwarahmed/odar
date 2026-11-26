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
    ora_user: Optional[str] = None
    ora_password: Optional[str] = None
    ora_dsn: Optional[str] = None
    ai_provider: str = "mock"
    ai_api_key: Optional[str] = None
    ai_model: str = "claude-sonnet-5-5"
    ai_max_tokens: int = 1500


@lru_cache
def get_settings() -> Settings:
    return Settings()
