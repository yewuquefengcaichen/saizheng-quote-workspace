from fastapi import APIRouter

from app.core.config import settings
from app.schemas.health import HealthCheck

router = APIRouter(prefix='/health', tags=['health'])


@router.get('', response_model=HealthCheck)
async def health_check() -> HealthCheck:
    return HealthCheck(
        status='ok',
        service_name=settings.app_name,
        environment=settings.environment,
        version=settings.app_version,
    )
