from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import settings
from app.core.logging import setup_logging


def create_application() -> FastAPI:
    setup_logging()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
    )

    @app.get('/', tags=['meta'])
    async def root() -> dict[str, str]:
        return {
            'service': settings.app_name,
            'version': settings.app_version,
            'environment': settings.environment,
            'status': 'ok',
        }

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_application()
