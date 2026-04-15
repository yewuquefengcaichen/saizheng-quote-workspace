from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.services.catalog_sync import LegacyCatalogSyncService, build_sync_job_summary, get_latest_catalog_sync_job


router = APIRouter(prefix='/catalog-sync', tags=['catalog-sync'])


class ManualCatalogSyncPayload(BaseModel):
    requested_by: str | None = Field(default='v2-api')
    source_type: str = Field(default='legacy_json_upload')
    source_name: str = Field(default='products_json_manual')
    limit: int | None = Field(default=None, ge=1)


@router.get('/latest')
async def get_latest_catalog_sync(session: AsyncSession = Depends(get_db_session)) -> dict:
    job = await get_latest_catalog_sync_job(session)
    return {
        'success': True,
        'job': build_sync_job_summary(job),
    }


@router.post('/manual')
async def run_manual_catalog_sync(
    payload: ManualCatalogSyncPayload,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    service = LegacyCatalogSyncService(
        session,
        dry_run=False,
        limit=payload.limit,
        source_type=payload.source_type,
        source_name=payload.source_name,
        requested_by=payload.requested_by,
    )
    result = await service.run_from_default_file()
    return {
        'success': True,
        **result,
    }
