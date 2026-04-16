from __future__ import annotations

import asyncio
import gc
from dataclasses import asdict, dataclass
from typing import Any

from app.core.celery_app import celery_app
from app.db.session import AsyncSessionLocal
from app.services.image_embedding import (
    CLIP_PLACEHOLDER_MODEL_NAME,
    CLIP_PLACEHOLDER_PROVIDER,
    DEFAULT_EMBEDDING_MODEL_NAME,
    DEFAULT_EMBEDDING_PROVIDER,
    select_assets_for_embedding,
    upsert_clip_embedding,
    upsert_hash_embedding,
)


@dataclass
class ImageEmbeddingTaskStats:
    selected_assets: int = 0
    processed_assets: int = 0
    ready_embeddings: int = 0
    failed_assets: int = 0
    failed_examples: list[dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload['failed_examples'] = payload.get('failed_examples') or []
        return payload


def _release_torch_cache() -> None:
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


async def _generate_image_embeddings_async(
    *,
    provider: str,
    model_name: str,
    limit: int | None,
    only_missing: bool,
    commit_every: int,
    dry_run: bool,
) -> dict[str, Any]:
    stats = ImageEmbeddingTaskStats(failed_examples=[])
    async with AsyncSessionLocal() as session:
        assets = await select_assets_for_embedding(
            session,
            provider=provider,
            model_name=model_name,
            only_missing=only_missing,
            limit=limit,
        )
        stats.selected_assets = len(assets)

        for index, asset in enumerate(assets, start=1):
            stats.processed_assets += 1
            try:
                if provider == CLIP_PLACEHOLDER_PROVIDER:
                    await upsert_clip_embedding(
                        session,
                        asset=asset,
                        provider=provider,
                        model_name=model_name,
                    )
                else:
                    await upsert_hash_embedding(
                        session,
                        asset=asset,
                        provider=provider,
                        model_name=model_name,
                    )
                stats.ready_embeddings += 1
            except Exception as exc:
                stats.failed_assets += 1
                if stats.failed_examples is not None and len(stats.failed_examples) < 20:
                    stats.failed_examples.append(
                        {
                            'asset_id': asset.id,
                            'storage_key': asset.storage_key,
                            'error': str(exc)[:500],
                        }
                    )

            if index % commit_every == 0:
                if dry_run:
                    await session.flush()
                else:
                    await session.commit()
                _release_torch_cache()

        if dry_run:
            await session.rollback()
        else:
            await session.commit()
        _release_torch_cache()

    return stats.to_dict()


@celery_app.task(name='app.tasks.embedding.generate_image_embeddings', bind=True)
def generate_image_embeddings_task(
    self,
    provider: str = DEFAULT_EMBEDDING_PROVIDER,
    model_name: str | None = None,
    limit: int | None = 20,
    only_missing: bool = True,
    commit_every: int = 5,
    dry_run: bool = False,
) -> dict[str, Any]:
    provider = provider or DEFAULT_EMBEDDING_PROVIDER
    if provider == CLIP_PLACEHOLDER_PROVIDER:
        model_name = model_name or CLIP_PLACEHOLDER_MODEL_NAME
    else:
        model_name = model_name or DEFAULT_EMBEDDING_MODEL_NAME

    safe_limit = max(1, min(int(limit or 20), 1000))
    safe_commit_every = max(1, min(int(commit_every or 5), safe_limit))

    return asyncio.run(
        _generate_image_embeddings_async(
            provider=provider,
            model_name=model_name,
            limit=safe_limit,
            only_missing=bool(only_missing),
            commit_every=safe_commit_every,
            dry_run=bool(dry_run),
        )
    )
