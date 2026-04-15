from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.services.image_embedding import select_assets_for_embedding, upsert_hash_embedding  # noqa: E402


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
    ) -> None:
        self.limit = limit
        self.only_missing = only_missing
        self.dry_run = dry_run
        self.commit_every = commit_every
        self.stats = EmbeddingStats()

    async def run(self) -> None:
        async with AsyncSessionLocal() as session:
            assets = await select_assets_for_embedding(
                session,
                provider=settings.image_embedding_provider,
                model_name=settings.image_embedding_model_name,
                only_missing=self.only_missing,
                limit=self.limit,
            )
            self.stats.selected_assets = len(assets)
            print(
                f'[image-embedding] selected_assets={self.stats.selected_assets} '
                f'provider={settings.image_embedding_provider} model={settings.image_embedding_model_name}'
            )

            for index, asset in enumerate(assets, start=1):
                self.stats.processed_assets += 1
                try:
                    await upsert_hash_embedding(
                        session,
                        asset=asset,
                        provider=settings.image_embedding_provider,
                        model_name=settings.image_embedding_model_name,
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

            if self.dry_run:
                await session.rollback()
                print('[image-embedding] dry-run complete, transaction rolled back')
            else:
                await session.commit()
                print('[image-embedding] generation committed')

        print(asdict(self.stats))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='根据 image_assets 里的 phash/dhash 生成 128 维图片向量。')
    parser.add_argument('--limit', type=int, default=None, help='最多处理多少个 image_assets')
    parser.add_argument('--all', action='store_true', help='忽略 only-missing，全部重建')
    parser.add_argument('--dry-run', action='store_true', help='只验证，不提交事务')
    parser.add_argument('--commit-every', type=int, default=500, help='每处理多少条提交一次')
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    generator = ImageEmbeddingGenerator(
        limit=args.limit,
        only_missing=not args.all,
        dry_run=args.dry_run,
        commit_every=max(1, args.commit_every),
    )
    await generator.run()


if __name__ == '__main__':
    asyncio.run(main())
