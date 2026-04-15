from fastapi import APIRouter

from app.api.routes.catalog_sync import router as catalog_sync_router
from app.api.routes.health import router as health_router
from app.api.routes.image_search import router as image_search_router

api_router = APIRouter()
api_router.include_router(catalog_sync_router)
api_router.include_router(health_router)
api_router.include_router(image_search_router)
