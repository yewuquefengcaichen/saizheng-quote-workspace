from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import importlib.util
import importlib
from io import BytesIO
from pathlib import Path
import re

import imagehash
from PIL import Image, UnidentifiedImageError
from sqlalchemy import Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Brand, Category, ImageAsset, ImageEmbedding, MatchFeedback, Product, ProductImage, ProductVariant
from app.services.image_pipeline import get_archive_root


DEFAULT_EMBEDDING_PROVIDER = settings.image_embedding_provider
DEFAULT_EMBEDDING_MODEL_NAME = settings.image_embedding_model_name
DEFAULT_EMBEDDING_VECTOR_DIM = settings.image_embedding_vector_dim
HASH_EMBEDDING_VECTOR_DIM = 128
SUPPORTED_VECTOR_DIMS = {128, 512}
CLIP_PLACEHOLDER_PROVIDER = 'clip_local'
CLIP_PLACEHOLDER_MODEL_NAME = 'openclip_vit_b_32_512d'
CLIP_PLACEHOLDER_VECTOR_DIM = 512
CLIP_MODEL_ALIASES = {
    CLIP_PLACEHOLDER_MODEL_NAME: ('ViT-B-32', 'openai'),
}
IMAGE_FEEDBACK_RERANK_MAX_BOOST = 0.08
IMAGE_FEEDBACK_CONFIRM_COUNT_SATURATION = 6
IMAGE_FEEDBACK_WEIGHT_SATURATION_DELTA = 0.4


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


@dataclass(slots=True)
class ImageEmbeddingProviderStatus:
    provider: str
    model_name: str
    vector_dim: int
    active: bool
    available: bool
    schema_supported: bool
    ready_embeddings: int
    total_ready_assets: int
    pending_assets: int
    missing_dependency: str | None = None
    note: str | None = None


@dataclass(slots=True)
class ClipRuntime:
    model: object
    preprocess: object
    device: str
    model_arch: str
    pretrained: str


def hex_hash_to_bit_vector(hash_hex: str) -> list[float]:
    normalized = str(hash_hex or '').strip().lower()
    if not normalized:
        raise ValueError('empty hash value')
    return [1.0 if bit == '1' else -1.0 for nibble in normalized for bit in f'{int(nibble, 16):04b}']


def build_hash_embedding_vector(phash: str, dhash: str) -> list[float]:
    vector = hex_hash_to_bit_vector(phash) + hex_hash_to_bit_vector(dhash)
    if len(vector) != HASH_EMBEDDING_VECTOR_DIM:
        raise ValueError(f'unexpected vector dim: {len(vector)}')
    return vector


def normalize_vector(values: list[float]) -> list[float]:
    norm = sum(float(value) * float(value) for value in values) ** 0.5
    if norm <= 0:
        return values
    return [float(value) / norm for value in values]


def get_embedding_vector_column(vector_dim: int):
    if int(vector_dim) == 128:
        return ImageEmbedding.embedding_vector
    if int(vector_dim) == 512:
        return ImageEmbedding.embedding_vector_512
    raise ValueError(f'unsupported embedding vector dim: {vector_dim}')


def is_embedding_schema_supported(vector_dim: int) -> bool:
    try:
        get_embedding_vector_column(vector_dim)
        return True
    except Exception:
        return False


def _module_importable(module_name: str) -> bool:
    if importlib.util.find_spec(module_name) is None:
        return False
    try:
        importlib.import_module(module_name)
        return True
    except Exception:
        return False


def resolve_clip_model(model_name: str) -> tuple[str, str]:
    normalized = str(model_name or CLIP_PLACEHOLDER_MODEL_NAME)
    if normalized in CLIP_MODEL_ALIASES:
        return CLIP_MODEL_ALIASES[normalized]
    if '::' in normalized:
        model_arch, pretrained = normalized.split('::', 1)
        return model_arch.strip(), pretrained.strip()
    return 'ViT-B-32', 'openai'


@lru_cache(maxsize=2)
def load_clip_runtime(model_name: str = CLIP_PLACEHOLDER_MODEL_NAME) -> ClipRuntime:
    try:
        import torch
        import open_clip
    except Exception as exc:  # pragma: no cover - optional heavyweight deps
        raise RuntimeError('CLIP 依赖未安装，请安装 torch 与 open_clip_torch') from exc

    model_arch, pretrained = resolve_clip_model(model_name)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model, _, preprocess = open_clip.create_model_and_transforms(model_arch, pretrained=pretrained)
    model.eval()
    model.to(device)
    return ClipRuntime(
        model=model,
        preprocess=preprocess,
        device=device,
        model_arch=model_arch,
        pretrained=pretrained,
    )


def compute_clip_image_embedding_from_pil(image: Image.Image, *, model_name: str = CLIP_PLACEHOLDER_MODEL_NAME) -> list[float]:
    try:
        import torch
    except Exception as exc:  # pragma: no cover - optional heavyweight deps
        raise RuntimeError('CLIP 依赖未安装，请安装 torch') from exc

    runtime = load_clip_runtime(model_name)
    image_rgb = image.convert('RGB')
    image_tensor = runtime.preprocess(image_rgb).unsqueeze(0).to(runtime.device)
    with torch.no_grad():
        features = runtime.model.encode_image(image_tensor)
        features = features / features.norm(dim=-1, keepdim=True)
    vector = [float(value) for value in features.squeeze(0).detach().cpu().tolist()]
    if len(vector) != CLIP_PLACEHOLDER_VECTOR_DIM:
        raise ValueError(f'unexpected CLIP vector dim: {len(vector)}')
    return normalize_vector(vector)


def compute_clip_image_embedding_from_bytes(file_bytes: bytes, *, model_name: str = CLIP_PLACEHOLDER_MODEL_NAME) -> list[float]:
    try:
        with Image.open(BytesIO(file_bytes)) as image:
            return compute_clip_image_embedding_from_pil(image, model_name=model_name)
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f'无法识别上传图片: {exc}') from exc


def compute_clip_image_embedding_from_file(file_path: Path, *, model_name: str = CLIP_PLACEHOLDER_MODEL_NAME) -> list[float]:
    try:
        with Image.open(file_path) as image:
            return compute_clip_image_embedding_from_pil(image, model_name=model_name)
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f'无法识别归档图片 {file_path}: {exc}') from exc


def get_embedding_provider_registry() -> list[dict[str, object]]:
    clip_deps_available = _module_importable('torch') and _module_importable('open_clip')
    return [
        {
            'provider': DEFAULT_EMBEDDING_PROVIDER,
            'model_name': DEFAULT_EMBEDDING_MODEL_NAME,
            'vector_dim': DEFAULT_EMBEDDING_VECTOR_DIM,
            'available': True,
            'missing_dependency': None,
            'note': '当前生产可用的 phash + dhash 128 维本地图片近似检索。',
        },
        {
            'provider': CLIP_PLACEHOLDER_PROVIDER,
            'model_name': CLIP_PLACEHOLDER_MODEL_NAME,
            'vector_dim': CLIP_PLACEHOLDER_VECTOR_DIM,
            'available': clip_deps_available,
            'missing_dependency': None if clip_deps_available else '需要安装可正常导入的 torch 与 open_clip_torch。',
            'note': 'CLIP 语义视觉检索预留位；数据库已预留 embedding_vector_512，依赖和生成器就绪后可写入 512 维向量。',
        },
    ]


async def get_image_embedding_status(session: AsyncSession) -> list[ImageEmbeddingProviderStatus]:
    total_ready_assets = int(
        await session.scalar(
            select(func.count())
            .select_from(ImageAsset)
            .where(
                ImageAsset.archive_status == 'ready',
                ImageAsset.phash.is_not(None),
                ImageAsset.dhash.is_not(None),
            )
        )
        or 0
    )
    statuses: list[ImageEmbeddingProviderStatus] = []
    for provider_config in get_embedding_provider_registry():
        provider = str(provider_config['provider'])
        model_name = str(provider_config['model_name'])
        vector_dim = int(provider_config['vector_dim'])
        schema_supported = is_embedding_schema_supported(vector_dim)
        vector_column = get_embedding_vector_column(vector_dim) if schema_supported else None
        ready_embeddings = int(
            await session.scalar(
                select(func.count())
                .select_from(ImageEmbedding)
                .where(
                    ImageEmbedding.provider == provider,
                    ImageEmbedding.model_name == model_name,
                    ImageEmbedding.vector_dim == vector_dim,
                    ImageEmbedding.vector_status == 'ready',
                    vector_column.is_not(None),
                )
            )
            if vector_column is not None
            else 0
        )
        statuses.append(
            ImageEmbeddingProviderStatus(
                provider=provider,
                model_name=model_name,
                vector_dim=vector_dim,
                active=provider == DEFAULT_EMBEDDING_PROVIDER and model_name == DEFAULT_EMBEDDING_MODEL_NAME,
                available=bool(provider_config.get('available')),
                schema_supported=schema_supported,
                ready_embeddings=ready_embeddings,
                total_ready_assets=total_ready_assets,
                pending_assets=max(0, total_ready_assets - ready_embeddings),
                missing_dependency=provider_config.get('missing_dependency') or None,
                note=provider_config.get('note') or None,
            )
        )
    return statuses


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


def _normalize_feedback_product_code(value: str | None) -> str:
    return str(value or '').strip()


def _compute_feedback_boost(confirm_count: int, avg_feedback_weight: float) -> float:
    safe_count = max(0, int(confirm_count or 0))
    safe_avg_weight = max(1.0, float(avg_feedback_weight or 1.0))
    count_factor = min(1.0, safe_count / IMAGE_FEEDBACK_CONFIRM_COUNT_SATURATION)
    weight_factor = min(1.0, (safe_avg_weight - 1.0) / IMAGE_FEEDBACK_WEIGHT_SATURATION_DELTA)
    blended = count_factor * 0.7 + weight_factor * 0.3
    return max(0.0, min(IMAGE_FEEDBACK_RERANK_MAX_BOOST, blended * IMAGE_FEEDBACK_RERANK_MAX_BOOST))


async def _load_feedback_boost_by_product_id(
    session: AsyncSession,
    *,
    product_id_to_code: dict[int, str],
) -> dict[int, float]:
    code_to_product_ids: dict[str, set[int]] = {}
    for product_id, product_code in product_id_to_code.items():
        normalized_code = _normalize_feedback_product_code(product_code)
        if not normalized_code:
            continue
        code_to_product_ids.setdefault(normalized_code, set()).add(int(product_id))
    if not code_to_product_ids:
        return {}

    feedback_rows = (
        await session.execute(
            select(
                MatchFeedback.selected_product_code,
                func.count(MatchFeedback.id).label('confirm_count'),
                func.avg(func.coalesce(MatchFeedback.feedback_weight, 1.0)).label('avg_feedback_weight'),
            )
            .where(
                MatchFeedback.action == 'select',
                MatchFeedback.selected_product_code.in_(list(code_to_product_ids.keys())),
            )
            .group_by(MatchFeedback.selected_product_code)
        )
    ).all()

    boost_by_product_id: dict[int, float] = {}
    for row in feedback_rows:
        normalized_code = _normalize_feedback_product_code(row.selected_product_code)
        if not normalized_code:
            continue
        boost = _compute_feedback_boost(
            confirm_count=int(row.confirm_count or 0),
            avg_feedback_weight=float(row.avg_feedback_weight or 1.0),
        )
        if boost <= 0:
            continue
        for product_id in code_to_product_ids.get(normalized_code, set()):
            boost_by_product_id[int(product_id)] = boost
    return boost_by_product_id


def rerank_image_candidates(
    candidates: list[ImageSearchCandidateResult],
    *,
    query_text: str | None = None,
    spec_hint: str | None = None,
    brand_hint: str | None = None,
    feedback_boost_by_product_id: dict[int, float] | None = None,
) -> list[ImageSearchCandidateResult]:
    has_hint = any(str(value or '').strip() for value in [query_text, spec_hint, brand_hint])
    feedback_boost_by_product_id = feedback_boost_by_product_id or {}
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

        feedback_boost = 0.0
        if item.product_id is not None:
            feedback_boost = float(feedback_boost_by_product_id.get(int(item.product_id), 0.0) or 0.0)
        if feedback_boost > 0:
            rerank_score += feedback_boost
            reasons.append(f'馈+{round(feedback_boost * 100)}')

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


def compute_query_image_features_for_provider(
    file_bytes: bytes,
    *,
    provider: str = DEFAULT_EMBEDDING_PROVIDER,
    model_name: str = DEFAULT_EMBEDDING_MODEL_NAME,
) -> QueryImageFeatures:
    features = compute_query_image_features(file_bytes)
    if provider == CLIP_PLACEHOLDER_PROVIDER:
        return QueryImageFeatures(
            phash=features.phash,
            dhash=features.dhash,
            vector=compute_clip_image_embedding_from_bytes(file_bytes, model_name=model_name),
            width=features.width,
            height=features.height,
        )
    return features


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
    embedding.embedding_vector_512 = None
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


async def upsert_clip_embedding(
    session: AsyncSession,
    *,
    asset: ImageAsset,
    provider: str = CLIP_PLACEHOLDER_PROVIDER,
    model_name: str = CLIP_PLACEHOLDER_MODEL_NAME,
) -> ImageEmbedding:
    archive_path = resolve_archive_file_path(asset.storage_key)
    if archive_path is None:
        raise ValueError(f'asset {asset.id} 归档文件不存在')

    vector = compute_clip_image_embedding_from_file(archive_path, model_name=model_name)
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

    model_arch, pretrained = resolve_clip_model(model_name)
    embedding.vector_dim = len(vector)
    embedding.vector_status = 'ready'
    embedding.embedding_vector = None
    embedding.embedding_vector_512 = vector
    embedding.embedding_json = {
        'strategy': 'open_clip_image_embedding',
        'model_arch': model_arch,
        'pretrained': pretrained,
        'normalized': True,
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
    stmt: Select = select(ImageAsset).where(ImageAsset.archive_status == 'ready').order_by(ImageAsset.id)
    if provider == CLIP_PLACEHOLDER_PROVIDER:
        stmt = stmt.where(ImageAsset.storage_key.is_not(None))
    else:
        stmt = stmt.where(
            ImageAsset.phash.is_not(None),
            ImageAsset.dhash.is_not(None),
        )

    if only_missing:
        stmt = stmt.where(
            ~ImageAsset.embeddings.any(
                and_(
                    ImageEmbedding.provider == provider,
                    ImageEmbedding.model_name == model_name,
                    ImageEmbedding.vector_dim == (CLIP_PLACEHOLDER_VECTOR_DIM if provider == CLIP_PLACEHOLDER_PROVIDER else HASH_EMBEDDING_VECTOR_DIM),
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
    retrieval_limit = max(
        top_k * (10 if provider == DEFAULT_EMBEDDING_PROVIDER and has_rerank_hint else 6 if has_rerank_hint else 4),
        24,
    )
    vector_column = get_embedding_vector_column(len(query_vector))
    embedding_rows = (
        await session.execute(
            select(
                ImageEmbedding.asset_id,
                vector_column.cosine_distance(query_vector).label('distance'),
            )
            .where(
                ImageEmbedding.provider == provider,
                ImageEmbedding.model_name == model_name,
                ImageEmbedding.vector_dim == len(query_vector),
                ImageEmbedding.vector_status == 'ready',
                vector_column.is_not(None),
            )
            .order_by('distance')
            .limit(retrieval_limit)
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

    sorted_product_rows = sorted(
        product_rows,
        key=lambda row: (
            float(distance_by_asset.get(int(row.asset_id), 999.0)),
            0 if bool(row.is_primary) else 1,
            int(row.asset_id),
        ),
    )

    for row in sorted_product_rows:
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
        if len(results) >= retrieval_limit:
            break

    product_id_to_code = {
        int(item.product_id): item.product_code
        for item in results
        if item.product_id is not None and _normalize_feedback_product_code(item.product_code)
    }
    feedback_boost_by_product_id = await _load_feedback_boost_by_product_id(
        session,
        product_id_to_code=product_id_to_code,
    ) if product_id_to_code else {}

    reranked_results = rerank_image_candidates(
        results,
        query_text=query_text,
        spec_hint=spec_hint,
        brand_hint=brand_hint,
        feedback_boost_by_product_id=feedback_boost_by_product_id,
    )
    return reranked_results[:top_k]
