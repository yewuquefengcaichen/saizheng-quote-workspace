from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import re

import imagehash
from PIL import Image, UnidentifiedImageError
from sqlalchemy import Select, and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Brand, Category, ImageAsset, ImageEmbedding, Product, ProductImage, ProductVariant
from app.services.image_pipeline import get_archive_root


DEFAULT_EMBEDDING_PROVIDER = settings.image_embedding_provider
DEFAULT_EMBEDDING_MODEL_NAME = settings.image_embedding_model_name
DEFAULT_EMBEDDING_VECTOR_DIM = settings.image_embedding_vector_dim


@dataclass(slots=True)
class QueryImageFeatures:
    phash: str
    dhash: str
    vector: list[float]
    width: int | None
    height: int | None


@dataclass(slots=True)
class ImageSearchCandidateResult:
    asset_id: int
    product_id: int | None
    variant_id: int | None
    product_code: str | None
    product_name: str | None
    variant_name: str | None
    brand_name: str | None
    category_name: str | None
    similarity: float
    distance: float
    image_role: str | None
    is_primary: bool
    storage_key: str | None
    mime_type: str | None
    width: int | None
    height: int | None
    reference_price: float | None
    source_url: str | None
    resolved_url: str | None
    base_similarity: float | None = None
    rerank_score: float | None = None
    rerank_reason: str | None = None


def hex_hash_to_bit_vector(hash_hex: str) -> list[float]:
    normalized = str(hash_hex or '').strip().lower()
    if not normalized:
        raise ValueError('empty hash value')
    return [1.0 if bit == '1' else -1.0 for nibble in normalized for bit in f'{int(nibble, 16):04b}']


def build_hash_embedding_vector(phash: str, dhash: str) -> list[float]:
    vector = hex_hash_to_bit_vector(phash) + hex_hash_to_bit_vector(dhash)
    if len(vector) != DEFAULT_EMBEDDING_VECTOR_DIM:
        raise ValueError(f'unexpected vector dim: {len(vector)}')
    return vector


TOKEN_PATTERN = re.compile(r'[\u4e00-\u9fff]+|[a-z0-9]+', re.IGNORECASE)


def normalize_search_tokens(value: str | None) -> list[str]:
    text = str(value or '').strip().lower()
    if not text:
        return []
    tokens = TOKEN_PATTERN.findall(text)
    return [token for token in tokens if token]


def compute_token_overlap_score(query_text: str | None, candidate_text: str | None) -> float:
    query_tokens = normalize_search_tokens(query_text)
    candidate_tokens = set(normalize_search_tokens(candidate_text))
    if not query_tokens or not candidate_tokens:
        return 0.0

    matched = sum(1 for token in query_tokens if token in candidate_tokens)
    return min(1.0, matched / max(1, len(set(query_tokens))))


def compute_substring_bonus(query_text: str | None, candidate_text: str | None) -> float:
    query = str(query_text or '').strip().lower()
    candidate = str(candidate_text or '').strip().lower()
    if not query or not candidate:
        return 0.0
    if query == candidate:
        return 1.0
    if query in candidate:
        return 0.75
    return 0.0


def rerank_image_candidates(
    candidates: list[ImageSearchCandidateResult],
    *,
    query_text: str | None = None,
    spec_hint: str | None = None,
    brand_hint: str | None = None,
) -> list[ImageSearchCandidateResult]:
    has_hint = any(str(value or '').strip() for value in [query_text, spec_hint, brand_hint])
    reranked: list[ImageSearchCandidateResult] = []

    for item in candidates:
        image_score = max(0.0, min(1.0, float(item.similarity or 0.0)))
        text_corpus = ' '.join(
            value for value in [
                item.product_code,
                item.product_name,
                item.variant_name,
                item.brand_name,
                item.category_name,
            ] if value
        )
        query_text_score = max(
            compute_token_overlap_score(query_text, text_corpus),
            compute_substring_bonus(query_text, text_corpus),
        )
        spec_score = max(
            compute_token_overlap_score(spec_hint, item.variant_name),
            compute_substring_bonus(spec_hint, item.variant_name),
        )
        brand_score = max(
            compute_token_overlap_score(brand_hint, item.brand_name),
            compute_substring_bonus(brand_hint, item.brand_name),
        )

        rerank_score = image_score
        reasons = [f'图{round(image_score * 100)}']
        if has_hint:
            rerank_score = (
                image_score * 0.62
                + query_text_score * 0.24
                + spec_score * 0.10
                + brand_score * 0.04
            )
            if query_text_score > 0:
                reasons.append(f'词{round(query_text_score * 100)}')
            if spec_score > 0:
                reasons.append(f'规{round(spec_score * 100)}')
            if brand_score > 0:
                reasons.append(f'牌{round(brand_score * 100)}')

        reranked.append(
            ImageSearchCandidateResult(
                asset_id=item.asset_id,
                product_id=item.product_id,
                variant_id=item.variant_id,
                product_code=item.product_code,
                product_name=item.product_name,
                variant_name=item.variant_name,
                brand_name=item.brand_name,
                category_name=item.category_name,
                similarity=min(1.0, max(0.0, rerank_score)),
                distance=item.distance,
                image_role=item.image_role,
                is_primary=item.is_primary,
                storage_key=item.storage_key,
                mime_type=item.mime_type,
                width=item.width,
                height=item.height,
                reference_price=item.reference_price,
                source_url=item.source_url,
                resolved_url=item.resolved_url,
                base_similarity=image_score,
                rerank_score=min(1.0, max(0.0, rerank_score)),
                rerank_reason=' · '.join(reasons),
            )
        )

    reranked.sort(
        key=lambda item: (
            float(item.rerank_score if item.rerank_score is not None else item.similarity or 0.0),
            float(item.base_similarity if item.base_similarity is not None else item.similarity or 0.0),
            bool(item.is_primary),
        ),
        reverse=True,
    )
    return reranked


def compute_query_image_features(file_bytes: bytes) -> QueryImageFeatures:
    try:
        with Image.open(BytesIO(file_bytes)) as image:
            width, height = image.size
            phash = str(imagehash.phash(image))
            dhash = str(imagehash.dhash(image))
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f'无法识别上传图片: {exc}') from exc

    return QueryImageFeatures(
        phash=phash,
        dhash=dhash,
        vector=build_hash_embedding_vector(phash=phash, dhash=dhash),
        width=width,
        height=height,
    )


def resolve_archive_file_path(storage_key: str | None) -> Path | None:
    if not storage_key:
        return None
    candidate = (get_archive_root() / storage_key).resolve()
    archive_root = get_archive_root().resolve()
    try:
        candidate.relative_to(archive_root)
    except ValueError:
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    return candidate


async def upsert_hash_embedding(
    session: AsyncSession,
    *,
    asset: ImageAsset,
    provider: str = DEFAULT_EMBEDDING_PROVIDER,
    model_name: str = DEFAULT_EMBEDDING_MODEL_NAME,
) -> ImageEmbedding:
    if not asset.phash or not asset.dhash:
        raise ValueError(f'asset {asset.id} 缺少 phash/dhash')

    vector = build_hash_embedding_vector(phash=asset.phash, dhash=asset.dhash)
    embedding = await session.scalar(
        select(ImageEmbedding).where(
            ImageEmbedding.asset_id == asset.id,
            ImageEmbedding.provider == provider,
            ImageEmbedding.model_name == model_name,
        )
    )
    if embedding is None:
        embedding = ImageEmbedding(
            asset_id=asset.id,
            provider=provider,
            model_name=model_name,
        )
        session.add(embedding)

    embedding.vector_dim = len(vector)
    embedding.vector_status = 'ready'
    embedding.embedding_vector = vector
    embedding.embedding_json = {
        'strategy': 'phash_plus_dhash_bits',
        'phash': asset.phash,
        'dhash': asset.dhash,
    }
    embedding.source_payload = {
        'asset_id': asset.id,
        'storage_key': asset.storage_key,
        'provider': provider,
        'model_name': model_name,
        'vector_dim': len(vector),
    }
    return embedding


async def select_assets_for_embedding(
    session: AsyncSession,
    *,
    provider: str = DEFAULT_EMBEDDING_PROVIDER,
    model_name: str = DEFAULT_EMBEDDING_MODEL_NAME,
    only_missing: bool = True,
    limit: int | None = None,
) -> list[ImageAsset]:
    stmt: Select = select(ImageAsset).where(
        ImageAsset.archive_status == 'ready',
        ImageAsset.phash.is_not(None),
        ImageAsset.dhash.is_not(None),
    ).order_by(ImageAsset.id)

    if only_missing:
        stmt = stmt.where(
            ~ImageAsset.embeddings.any(
                and_(
                    ImageEmbedding.provider == provider,
                    ImageEmbedding.model_name == model_name,
                    ImageEmbedding.vector_status == 'ready',
                )
            )
        )

    if limit is not None:
        stmt = stmt.limit(limit)

    return list((await session.scalars(stmt)).all())


async def search_similar_products(
    session: AsyncSession,
    *,
    query_vector: list[float],
    top_k: int = 12,
    provider: str = DEFAULT_EMBEDDING_PROVIDER,
    model_name: str = DEFAULT_EMBEDDING_MODEL_NAME,
    query_text: str | None = None,
    spec_hint: str | None = None,
    brand_hint: str | None = None,
) -> list[ImageSearchCandidateResult]:
    has_rerank_hint = any(str(value or '').strip() for value in [query_text, spec_hint, brand_hint])
    embedding_rows = (
        await session.execute(
            select(
                ImageEmbedding.asset_id,
                ImageEmbedding.embedding_vector.cosine_distance(query_vector).label('distance'),
            )
            .where(
                ImageEmbedding.provider == provider,
                ImageEmbedding.model_name == model_name,
                ImageEmbedding.vector_status == 'ready',
                ImageEmbedding.embedding_vector.is_not(None),
            )
            .order_by('distance')
            .limit(max(top_k * (6 if has_rerank_hint else 4), 24))
        )
    ).all()

    if not embedding_rows:
        return []

    distance_by_asset = {int(asset_id): float(distance) for asset_id, distance in embedding_rows}
    asset_ids = list(distance_by_asset)

    product_rows = (
        await session.execute(
            select(
                ProductImage.asset_id,
                ProductImage.variant_id,
                ProductImage.product_id,
                ProductImage.image_role,
                ProductImage.is_primary,
                Product.product_code,
                Product.name,
                Product.reference_price,
                Product.primary_image_url,
                ProductImage.resolved_url,
                ProductImage.source_url,
                ImageAsset.storage_key,
                ImageAsset.mime_type,
                ImageAsset.width,
                ImageAsset.height,
                ProductVariant.variant_name,
                Brand.name.label('brand_name'),
                Category.name.label('category_name'),
            )
            .join(ImageAsset, ImageAsset.id == ProductImage.asset_id)
            .join(Product, Product.id == ProductImage.product_id, isouter=True)
            .join(ProductVariant, ProductVariant.id == ProductImage.variant_id, isouter=True)
            .join(Brand, Brand.id == Product.brand_id, isouter=True)
            .join(Category, Category.id == Product.category_id, isouter=True)
            .where(ProductImage.asset_id.in_(asset_ids))
            .order_by(ProductImage.is_primary.desc(), ProductImage.sort_order.asc(), ProductImage.id.asc())
        )
    ).all()

    results: list[ImageSearchCandidateResult] = []
    seen_products: set[int] = set()

    for row in product_rows:
        asset_id = int(row.asset_id)
        distance = distance_by_asset.get(asset_id)
        if distance is None:
            continue

        product_id = int(row.product_id) if row.product_id is not None else None
        if product_id is not None and product_id in seen_products:
            continue
        if product_id is not None:
            seen_products.add(product_id)

        similarity = min(1.0, max(0.0, 1.0 - distance))
        results.append(
            ImageSearchCandidateResult(
                asset_id=asset_id,
                product_id=product_id,
                variant_id=int(row.variant_id) if row.variant_id is not None else None,
                product_code=row.product_code,
                product_name=row.name,
                variant_name=row.variant_name,
                brand_name=row.brand_name,
                category_name=row.category_name,
                similarity=similarity,
                distance=distance,
                image_role=row.image_role,
                is_primary=bool(row.is_primary),
                storage_key=row.storage_key,
                mime_type=row.mime_type,
                width=row.width,
                height=row.height,
                reference_price=float(row.reference_price) if row.reference_price is not None else None,
                source_url=row.source_url or row.primary_image_url,
                resolved_url=row.resolved_url,
            )
        )
        if len(results) >= top_k:
            break

    reranked_results = rerank_image_candidates(
        results,
        query_text=query_text,
        spec_hint=spec_hint,
        brand_hint=brand_hint,
    )
    return reranked_results[:top_k]
