from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = '??????? V2 API'
    app_version: str = '0.1.0'
    environment: str = 'development'
    debug: bool = True
    api_v1_prefix: str = '/api/v1'
    database_url: str = 'postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/saizheng_quote_v2'
    redis_url: str = 'redis://127.0.0.1:6379/0'
    sqlalchemy_echo: bool = False
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    model_config = SettingsConfigDict(
        env_prefix='SAIZHENG_',
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
