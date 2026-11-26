from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="/etc/odar/odar.env", env_prefix="ODAR_", extra="ignore"
    )
    env: str = "lab"
    log_dir: str = "/var/log/odar"
    log_level: str = "INFO"
    read_only: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
