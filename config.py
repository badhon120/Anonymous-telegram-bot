from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List, Any

class Settings(BaseSettings):
    BOT_TOKEN: str = "8987471728:AAFTrRlEh8rcKbHLNUIMMq8Ly0JAqjtL-0c"
    ADMIN_IDS: List[int] = []
    REQUIRED_CHANNEL_ID: int = 0
    DB_URL: str = "sqlite:///./data/db.sqlite3"
    
    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v: Any) -> List[int]:
        if isinstance(v, str):
            if not v.strip():
                return []
            # Handle comma-separated list
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        if isinstance(v, int):
            return [v]
        return v

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

config = Settings()
