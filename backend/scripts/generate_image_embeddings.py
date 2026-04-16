from __future__ import annotations

import argparse
import asyncio
import gc
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.services.image_embedding import (  # noqa: E402
    CLIP_PLACEHOLDER_MODEL_NAME,
    CLIP_PLACEHOLDER_PROVIDER,
    DEFAULT_EMBEDDING_MODEL_NAME,
    DEFAULT_EMBEDDING_PROVIDER,
    get_image_embedding_status,
    select_assets_for_embedding,
    upsert_clip_embedding,
    upsert_hash_embedding,
)


@dataclass
class EmbeddingStats:
    selected_assets: int = 0
    processed_assets: int = 0
    ready_embeddings: int = 0
    failed_assets: int = 0


class ImageEmbeddingGenerator:
    def __init__(
        self,
        *,
        limit: int | None,
        only_missing: bool,
        dry_run: bool,
        commit_every: int,
        provider: str,
        model_name: str,
    ) -> None:
        self.limit = limit
        self.only_missing = only_missing
        self.dry_run = dry_run
        self.commit_every = commit_every
        self.provider = provider
        self.model_name = model_name
        self.stats = EmbeddingStats()

    async def run(self) -> None:
        async with AsyncSessionLocal() as session:
            if self.provider != DEFAULT_EMBEDDING_PROVIDER and self.provider != CLIP_PLACEHOLDER_PROVIDER:
                print(f'[image-embedding] 暂不支持生成 provider={self.provider} model={self.model_name}')
                return

            if self.provider == CLIP_PLACEHOLDER_PROVIDER:
                self._print_clip_runtime_info()
                statuses = await get_image_embedding_status(session)
                matched = [item for item in statuses if item.provider == self.provider and item.model_name == self.model_name]
                if matched:
                    item = matched[0]
                    print(
                        f'[image-embedding] provider={item.provider} model={item.model_name} '
                        f'available={item.available} schema_supported={item.schema_supported} '
                        f'missing_dependency={item.missing_dependency or ""}'
                    )
                    if not item.schema_supported:
                        print('[image-embedding] 数据库结构暂不支持该 provider，请先执行 Alembic 迁移。')
                        return
                    if not item.available:
                        print('[image-embedding] 依赖暂不可用，请先安装 torch 与 open_clip_torch。')
                        return

            assets = await select_assets_for_embedding(
                session,
                provider=self.provider,
                model_name=self.model_name,
                only_missing=self.only_missing,
                limit=self.limit,
            )
            self.stats.selected_assets = len(assets)
            print(
                f'[image-embedding] selected_assets={self.stats.selected_assets} '
                f'provider={self.provider} model={self.model_name}'
            )

            for index, asset in enumerate(assets, start=1):
                self.stats.processed_assets += 1
                try:
                    if self.provider == CLIP_PLACEHOLDER_PROVIDER:
                        await upsert_clip_embedding(
                            session,
                            asset=asset,
                            provider=self.provider,
                            model_name=self.model_name,
                        )
                    else:
                        await upsert_hash_embedding(
                            session,
                            asset=asset,
                            provider=self.provider,
                            model_name=self.model_name,
                        )
                    self.stats.ready_embeddings += 1
                except Exception as exc:
                    self.stats.failed_assets += 1
                    print(f'[image-embedding] asset_id={asset.id} failed: {exc}')

                if index % self.commit_every == 0:
                    if self.dry_run:
                        await session.flush()
                        print(f'[image-embedding] dry-run processed={index}')
                    else:
                        await session.commit()
                        print(f'[image-embedding] committed processed={index}')
                    self._release_runtime_cache()

            if self.dry_run:
                await session.rollback()
                print('[image-embedding] dry-run complete, transaction rolled back')
            else:
                await session.commit()
                print('[image-embedding] generation committed')

        print(asdict(self.stats))

    def _print_clip_runtime_info(self) -> None:
        try:
            import torch
            print(
                '[image-embedding] torch='
                f'{torch.__version__} cuda_available={torch.cuda.is_available()} '
                f'cuda={torch.version.cuda} '
                f'device={torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"}',
                flush=True,
            )
        except Exception as exc:
            print(f'[image-embedding] torch runtime check failed: {exc}', flush=True)

    def _release_runtime_cache(self) -> None:
        gc.collect()
        if self.provider != CLIP_PLACEHOLDER_PROVIDER:
            return
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='根据 image_assets 生成图片向量；默认生成 128 维 hash，也可生成 512 维 CLIP。')
    parser.add_argument('--limit', type=int, default=None, help='最多处理多少个 image_assets')
    parser.add_argument('--all', action='store_true', help='忽略 only-missing，全部重建')
    parser.add_argument('--dry-run', action='store_true', help='只验证，不提交事务')
    parser.add_argument('--commit-every', type=int, default=500, help='每处理多少条提交一次')
    parser.add_argument('--provider', default=settings.image_embedding_provider, help=f'embedding provider，可选 {DEFAULT_EMBEDDING_PROVIDER} / {CLIP_PLACEHOLDER_PROVIDER}')
    parser.add_argument('--model-name', default=None, help='embedding model name；不填时根据 provider 自动选择')
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    generator = ImageEmbeddingGenerator(
        limit=args.limit,
        only_missing=not args.all,
        dry_run=args.dry_run,
        commit_every=max(1, args.commit_every),
        provider=args.provider or DEFAULT_EMBEDDING_PROVIDER,
        model_name=args.model_name or (CLIP_PLACEHOLDER_MODEL_NAME if (args.provider or DEFAULT_EMBEDDING_PROVIDER) == CLIP_PLACEHOLDER_PROVIDER else DEFAULT_EMBEDDING_MODEL_NAME),
    )
    await generator.run()


if __name__ == '__main__':
    asyncio.run(main())
