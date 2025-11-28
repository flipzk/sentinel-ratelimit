from enum import StrEnum
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class StrategyType(StrEnum):
    TOKEN_BUCKET = "token_bucket"
    SLIDING_WINDOW = "sliding_window"

class Settings(BaseSettings):
    app_name: str = "Sentinel API"
    redis_url: str
    rate_limit_strategy: StrategyType = StrategyType.TOKEN_BUCKET
    rate_limit_default: int = 100
    rate_limit_window: int = 60

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

@lru_cache
def get_settings() -> Settings:
    return Settings()