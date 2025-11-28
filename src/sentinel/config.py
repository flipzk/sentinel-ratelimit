from enum import Enum

from pydantic_settings import BaseSettings


class StrategyType(str, Enum):
    TOKEN_BUCKET = "token_bucket"
    SLIDING_WINDOW = "sliding_window"


class Settings(BaseSettings):
    app_name: str = "Sentinel"
    debug: bool = False

    rate_limit_strategy: StrategyType = StrategyType.TOKEN_BUCKET
    rate_limit_default: int = 100
    rate_limit_window: int = 60

    redis_url: str = "redis://localhost:6379"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
