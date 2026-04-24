from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ANTHROPIC_API_KEY: str = ""
    DATA_ROOT: Path = Path("./runtime")
    MAX_DATA_DOWNLOAD_GB: float = Field(default=2.0, ge=0.1)
    USE_FALLBACK: bool = False

    AGENT_ID_PAPER_ANALYST: Optional[str] = None
    AGENT_ID_CODE_AUDITOR: Optional[str] = None
    AGENT_ID_VALIDATOR: Optional[str] = None
    AGENT_ID_REVIEWER: Optional[str] = None
    MANAGED_ENVIRONMENT_ID: Optional[str] = None

    HOST: str = "0.0.0.0"
    PORT: int = 8000
    LOG_LEVEL: str = "info"

    def data_root_path(self) -> Path:
        path = self.DATA_ROOT.resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
