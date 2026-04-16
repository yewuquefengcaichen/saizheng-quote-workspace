from __future__ import annotations

from pydantic import BaseModel, Field


class ImageSearchCandidate(BaseModel):
    asset_id: int
    product_id: int | None = None
    variant_id: int | None = None
    product_code: str | None = None
    product_name: str | None = None
    variant_name: str | None = None
    brand_name: str | None = None
    category_name: str | None = None
    similarity: float = Field(..., ge=0.0, le=1.0)
    distance: float = Field(..., ge=0.0)
    image_role: str | None = None
    is_primary: bool = False
    storage_key: str | None = None
    archive_file_url: str | None = None
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    reference_price: float | None = None
    source_url: str | None = None
    resolved_url: str | None = None
    base_similarity: float | None = Field(default=None, ge=0.0, le=1.0)
    rerank_score: float | None = Field(default=None, ge=0.0, le=1.0)
    rerank_reason: str | None = None


class ImageSearchResponse(BaseModel):
    provider: str
    model_name: str
    vector_dim: int
    query_phash: str
    query_dhash: str
    query_width: int | None = None
    query_height: int | None = None
    total: int
    candidates: list[ImageSearchCandidate]


class ImageEmbeddingProviderStatus(BaseModel):
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


class ImageEmbeddingStatusResponse(BaseModel):
    active_provider: str
    active_model_name: str
    active_vector_dim: int
    providers: list[ImageEmbeddingProviderStatus]
