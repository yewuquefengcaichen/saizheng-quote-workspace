from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db_session
from app.schemas.image_search import ImageSearchCandidate, ImageSearchResponse
from app.services import (
    DEFAULT_EMBEDDING_MODEL_NAME,
    DEFAULT_EMBEDDING_PROVIDER,
    DEFAULT_EMBEDDING_VECTOR_DIM,
    compute_query_image_features,
    resolve_archive_file_path,
    search_similar_products,
)

router = APIRouter(prefix='/image-search', tags=['image-search'])


@router.post('/query', response_model=ImageSearchResponse)
async def query_image_search(
    file: UploadFile = File(...),
    top_k: int = Form(default=12),
    session: AsyncSession = Depends(get_db_session),
) -> ImageSearchResponse:
    if top_k < 1 or top_k > 50:
        raise HTTPException(status_code=400, detail='top_k 必须在 1~50 之间')

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail='上传文件为空')

    try:
        query_features = compute_query_image_features(file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    candidates = await search_similar_products(
        session,
        query_vector=query_features.vector,
        top_k=top_k,
        provider=DEFAULT_EMBEDDING_PROVIDER,
        model_name=DEFAULT_EMBEDDING_MODEL_NAME,
    )

    response_candidates = [
        ImageSearchCandidate(
            asset_id=item.asset_id,
            product_id=item.product_id,
            variant_id=item.variant_id,
            product_code=item.product_code,
            product_name=item.product_name,
            variant_name=item.variant_name,
            brand_name=item.brand_name,
            category_name=item.category_name,
            similarity=item.similarity,
            distance=item.distance,
            image_role=item.image_role,
            is_primary=item.is_primary,
            storage_key=item.storage_key,
            archive_file_url=f'{settings.api_v1_prefix}/image-search/assets/{item.asset_id}/file',
            mime_type=item.mime_type,
            width=item.width,
            height=item.height,
            reference_price=item.reference_price,
            source_url=item.source_url,
            resolved_url=item.resolved_url,
        )
        for item in candidates
    ]

    return ImageSearchResponse(
        provider=DEFAULT_EMBEDDING_PROVIDER,
        model_name=DEFAULT_EMBEDDING_MODEL_NAME,
        vector_dim=DEFAULT_EMBEDDING_VECTOR_DIM,
        query_phash=query_features.phash,
        query_dhash=query_features.dhash,
        query_width=query_features.width,
        query_height=query_features.height,
        total=len(response_candidates),
        candidates=response_candidates,
    )


@router.get('/assets/{asset_id}/file')
async def get_archived_asset_file(asset_id: int, session: AsyncSession = Depends(get_db_session)) -> FileResponse:
    from sqlalchemy import select
    from app.models import ImageAsset

    asset = await session.scalar(select(ImageAsset).where(ImageAsset.id == asset_id))
    if asset is None:
        raise HTTPException(status_code=404, detail='图片资产不存在')

    file_path = resolve_archive_file_path(asset.storage_key)
    if file_path is None:
        raise HTTPException(status_code=404, detail='归档文件不存在')

    return FileResponse(
        path=file_path,
        media_type=asset.mime_type or 'application/octet-stream',
        filename=file_path.name,
    )
