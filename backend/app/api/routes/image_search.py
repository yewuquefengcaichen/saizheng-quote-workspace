from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db_session
from app.schemas.image_search import (
    ImageEmbeddingProviderStatus as ImageEmbeddingProviderStatusSchema,
    ImageEmbeddingStatusResponse,
    ImageSearchCandidate,
    ImageSearchResponse,
)
from app.services import (
    DEFAULT_EMBEDDING_MODEL_NAME,
    DEFAULT_EMBEDDING_PROVIDER,
    DEFAULT_EMBEDDING_VECTOR_DIM,
    compute_query_image_features_for_provider,
    get_image_embedding_status,
    resolve_archive_file_path,
    search_similar_products,
)

router = APIRouter(prefix='/image-search', tags=['image-search'])


@router.get('/embedding-status', response_model=ImageEmbeddingStatusResponse)
async def image_embedding_status(session: AsyncSession = Depends(get_db_session)) -> ImageEmbeddingStatusResponse:
    providers = await get_image_embedding_status(session)
    return ImageEmbeddingStatusResponse(
        active_provider=DEFAULT_EMBEDDING_PROVIDER,
        active_model_name=DEFAULT_EMBEDDING_MODEL_NAME,
        active_vector_dim=DEFAULT_EMBEDDING_VECTOR_DIM,
        providers=[
            ImageEmbeddingProviderStatusSchema(
                provider=item.provider,
                model_name=item.model_name,
                vector_dim=item.vector_dim,
                active=item.active,
                available=item.available,
                schema_supported=item.schema_supported,
                ready_embeddings=item.ready_embeddings,
                total_ready_assets=item.total_ready_assets,
                pending_assets=item.pending_assets,
                missing_dependency=item.missing_dependency,
                note=item.note,
            )
            for item in providers
        ],
    )


@router.post('/query', response_model=ImageSearchResponse)
async def query_image_search(
    file: UploadFile = File(...),
    top_k: int = Form(default=12),
    query_text: str | None = Form(default=None),
    spec_hint: str | None = Form(default=None),
    brand_hint: str | None = Form(default=None),
    provider: str | None = Form(default=None),
    model_name: str | None = Form(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> ImageSearchResponse:
    if top_k < 1 or top_k > 50:
        raise HTTPException(status_code=400, detail='top_k 必须在 1~50 之间')

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail='上传文件为空')

    selected_provider = provider or DEFAULT_EMBEDDING_PROVIDER
    selected_model_name = model_name or DEFAULT_EMBEDDING_MODEL_NAME

    try:
        query_features = compute_query_image_features_for_provider(
            file_bytes,
            provider=selected_provider,
            model_name=selected_model_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    candidates = await search_similar_products(
        session,
        query_vector=query_features.vector,
        top_k=top_k,
        provider=selected_provider,
        model_name=selected_model_name,
        query_text=query_text,
        spec_hint=spec_hint,
        brand_hint=brand_hint,
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
            base_similarity=item.base_similarity,
            rerank_score=item.rerank_score,
            rerank_reason=item.rerank_reason,
        )
        for item in candidates
    ]

    return ImageSearchResponse(
        provider=selected_provider,
        model_name=selected_model_name,
        vector_dim=len(query_features.vector) or DEFAULT_EMBEDDING_VECTOR_DIM,
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
