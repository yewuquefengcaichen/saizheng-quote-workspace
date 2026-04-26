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
from app.services.image_embedding import (  # noqa: E402
    CLIP_PLACEHOLDER_MODEL_NAME,
    CLIP_PLACEHOLDER_PROVIDER,
    DEFAULT_EMBEDDING_MODEL_NAME,
    DEFAULT_EMBEDDING_PROVIDER,
)
from generate_image_embeddings import ImageEmbeddingGenerator  # noqa: E402


@dataclass
class BatchTotals:
    batches: int = 0
    selected_assets: int = 0
    processed_assets: int = 0
    ready_embeddings: int = 0
    failed_assets: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='分批生成图片 embedding，适合全量 CLIP 向量慢速跑完。')
    parser.add_argument('--provider', default=settings.image_embedding_provider, help=f'embedding provider，可选 {DEFAULT_EMBEDDING_PROVIDER} / {CLIP_PLACEHOLDER_PROVIDER}')
    parser.add_argument('--model-name', default=None, help='embedding model name；不填时按 provider 自动选择')
    parser.add_argument('--batch-size', type=int, default=20, help='每批最多处理多少个资产')
    parser.add_argument('--max-batches', type=int, default=None, help='最多跑多少批；不填则直到没有待处理资产')
    parser.add_argument('--sleep-seconds', type=float, default=1.0, help='批次间 sleep 秒数，默认 1 秒')
    parser.add_argument('--commit-every', type=int, default=5, help='单批内每处理多少条提交一次')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--all', action='store_true', help='忽略 only-missing，按批重建')
    group.add_argument('--only-missing', action='store_true', help='只处理缺失向量资产（默认）')
    return parser.parse_args()


def resolve_model_name(provider: str, model_name: str | None) -> str:
    if model_name:
        return model_name
    if provider == CLIP_PLACEHOLDER_PROVIDER:
        return CLIP_PLACEHOLDER_MODEL_NAME
    return DEFAULT_EMBEDDING_MODEL_NAME


async def run_batches(args: argparse.Namespace) -> None:
    provider = args.provider or DEFAULT_EMBEDDING_PROVIDER
    model_name = resolve_model_name(provider, args.model_name)

    only_missing = True
    if args.all:
        only_missing = False
    if args.only_missing:
        only_missing = True

    batch_size = max(1, int(args.batch_size or 20))
    commit_every = max(1, min(int(args.commit_every or 5), batch_size))
    max_batches = int(args.max_batches) if args.max_batches else None
    sleep_seconds = max(0.0, float(args.sleep_seconds or 0.0))

    if not only_missing and max_batches is None:
        max_batches = 1
        print('[batch-embedding] 检测到 --all 且未设置 --max-batches，已自动限制为 1 批，避免无限循环。')

    totals = BatchTotals()
    batch_index = 0

    print(
        f'[batch-embedding] start provider={provider} model={model_name} '
        f'batch_size={batch_size} only_missing={only_missing} '
        f'max_batches={max_batches or "until-empty"} sleep_seconds={sleep_seconds}'
    )

    while True:
        if max_batches is not None and batch_index >= max_batches:
            print(f'[batch-embedding] reach max_batches={max_batches}, stop.')
            break

        batch_index += 1
        generator = ImageEmbeddingGenerator(
            limit=batch_size,
            only_missing=only_missing,
            dry_run=False,
            commit_every=commit_every,
            provider=provider,
            model_name=model_name,
        )
        await generator.run()

        stats = generator.stats
        selected = int(stats.selected_assets or 0)
        ready = int(stats.ready_embeddings or 0)
        failed = int(stats.failed_assets or 0)
        processed = int(stats.processed_assets or 0)

        if selected == 0:
            print(f'[batch-embedding] batch={batch_index} selected=0, no pending assets, stop.')
            break

        totals.batches += 1
        totals.selected_assets += selected
        totals.processed_assets += processed
        totals.ready_embeddings += ready
        totals.failed_assets += failed

        print(
            f'[batch-embedding] batch={batch_index} '
            f'selected={selected} ready={ready} failed={failed} '
            f'processed={processed} '
            f'accumulated_processed={totals.processed_assets} '
            f'accumulated_ready={totals.ready_embeddings} '
            f'accumulated_failed={totals.failed_assets}'
        )

        if sleep_seconds > 0:
            await asyncio.sleep(sleep_seconds)

    print(f'[batch-embedding] done {asdict(totals)}')


async def main() -> None:
    args = parse_args()
    await run_batches(args)


if __name__ == '__main__':
    asyncio.run(main())
