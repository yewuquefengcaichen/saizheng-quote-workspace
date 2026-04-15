from functools import lru_cache
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = '赛正报价工作台 V2 API'
    app_version: str = '0.1.0'
    environment: str = 'development'
    debug: bool = True
    api_v1_prefix: str = '/api/v1'
    database_url: str = 'postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/saizheng_quote_v2'
    redis_url: str = 'redis://127.0.0.1:6379/0'
    sqlalchemy_echo: bool = False
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None
    legacy_mall_base_url: str = 'https://sz.dinghuovip.com'
    legacy_file_base_url: str = 'https://udeanfile.dinghuovip.com'
    image_archive_root: str = str((BASE_DIR / 'storage' / 'image_archive').resolve())
    image_archive_backend: str = 'local_fs'
    image_archive_bucket: str = 'saizheng-v2-image-archive'
    image_request_timeout_seconds: int = 20
    image_embedding_provider: str = 'local_hash_embedding'
    image_embedding_model_name: str = 'phash_dhash_128d_v1'
    image_embedding_vector_dim: int = 128

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
