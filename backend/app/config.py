from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite+aiosqlite:///./data/campus.db"
    agent_db_path: str = "./data/agent.db"
    upload_dir: str = "./data/uploads"
    public_origin: str = "http://127.0.0.1:5173"
    secure_cookie: bool = False
    registration_enabled: bool = True
    app_mode: Literal["local", "shared"] = "local"
    extension_dir: str = ""
    settings_file: str = ".env"
    model_provider: str = "openai"
    text_model: str = ""
    vision_model: str = ""
    model_api_key: str = ""
    model_base_url: str | None = None
    model_use_system_proxy: bool = True
    scut_adapter_path: str = ""

    def prepare(self):
        if self.database_url.startswith("sqlite"):
            Path(self.database_url.split("///", 1)[1]).parent.mkdir(
                parents=True, exist_ok=True
            )
        Path(self.agent_db_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.upload_dir).mkdir(parents=True, exist_ok=True)
