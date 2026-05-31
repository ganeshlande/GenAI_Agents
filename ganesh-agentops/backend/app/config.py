from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List
import json


class Settings(BaseSettings):
    APP_NAME: str = "Ganesh AgentOps"
    DEBUG: bool = False
    DATABASE_URL: str = "sqlite:///./data/agentops.db"

    # Accepts a JSON array string from .env: ["http://localhost:3000"]
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://frontend:3000"]

    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""       # optional: proactive notifications / restrict access
    TELEGRAM_WEBHOOK_URL: str = ""   # reserved for future webhook mode
    # Set to "true" on dev machines behind corporate proxies with broken certs
    TELEGRAM_SKIP_SSL_VERIFY: bool = False

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    model_config = {"env_file": ".env", "case_sensitive": True, "extra": "ignore"}


settings = Settings()
