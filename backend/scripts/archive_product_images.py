from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests
from sqlalchemy import Select, select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models import ImageAsset, ProductImage  # noqa: E402
from app.services.image_pipeline import download_and_archive_image, normalize_remote_image_url  # noqa: E402


DEFAULT_STATUSES = ('pending', 'failed')


@dataclass
class ArchiveStats:
    selected: int = 0
    processed: int = 0
    archived: int = 0
    failed: int = 0
    created_assets: int = 0
    reused_assets: int = 0
    relinked_from_cache: int = 0
    bytes_downloaded: int = 0


def merge_payload(existing: dict | None, extra: dict) -> dict:
    payload = dict(existing or {})
    payload.update(extra)
    return payload


class ProductImageArchiver:
    def __init__(
        self,
        *,
        limit: int | None,
        statuses: tuple[str, ...],
        force: bool,
        dry_run: bool,
        only_missing_asset: bool,
        commit_every: int,
    ) -> None:
        self.limit = limit
        self.statuses = statuses
        self.force = force
        self.dry_run = dry_run
        self.only_missing_asset = only_missing_asset
        self.commit_every = commit_every
        self.stats = ArchiveStats()
        self.source_asset_cache: dict[str, int] = {}
        self.resolved_asset_cache: dict[str, int] = {}

    async def run(self) -> None:
        requests_session = requests.Session()

        async with AsyncSessionLocal() as session:
            await self.warm_asset_cache(session)
            images = await self.fetch_images(session)
            self.stats.selected = len(images)
            print(
                f'[image-archive] selected={self.stats.selected} '
                f'archive_root={settings.image_archive_root} '
                f'cached_sources={len(self.source_asset_cache)} '
                f'backend={settings.image_archive_backend}'
            )

            for index, product_image in enumerate(images, start=1):
                await self.process_one(session, product_image, requests_session)

                if index % self.commit_every == 0:
                    if self.dry_run:
                        await session.flush()
                        print(f'[image-archive] dry-run processed={index}')
                    else:
                        await session.commit()
                        print(f'[image-archive] committed processed={index}')

            if self.dry_run:
                await session.rollback()
                print('[image-archive] dry-run complete, transaction rolled back')
            else:
                await session.commit()
                print('[image-archive] archive committed')

        requests_session.close()
        print(asdict(self.stats))

    async def warm_asset_cache(self, session) -> None:
        rows = await session.execute(
            select(ProductImage.source_url, ProductImage.resolved_url, ProductImage.asset_id).where(ProductImage.asset_id.is_not(None))
        )
        for source_url, resolved_url, asset_id in rows.all():
            if source_url and asset_id:
                self.source_asset_cache[str(source_url)] = int(asset_id)
            if resolved_url and asset_id:
                self.resolved_asset_cache[str(resolved_url)] = int(asset_id)

    async def fetch_images(self, session) -> list[ProductImage]:
        stmt: Select = select(ProductImage).order_by(ProductImage.id)

        if self.only_missing_asset:
            stmt = stmt.where(ProductImage.asset_id.is_(None))

        if not self.force:
            stmt = stmt.where(ProductImage.sync_status.in_(self.statuses))

        if self.limit is not None:
            stmt = stmt.limit(self.limit)

        return list((await session.scalars(stmt)).all())

    async def process_one(self, session, product_image: ProductImage, requests_session: requests.Session) -> None:
        self.stats.processed += 1
        now = datetime.now(timezone.utc)
        resolved_url = normalize_remote_image_url(product_image.source_url)

        cached_asset_id = self.source_asset_cache.get(product_image.source_url) or self.resolved_asset_cache.get(resolved_url)
        if cached_asset_id:
            cached_asset = await session.get(ImageAsset, cached_asset_id)
            if cached_asset is not None:
                self.apply_asset_to_product_image(
                    product_image=product_image,
                    asset=cached_asset,
                    now=now,
                    sync_message='linked_existing_asset_cache',
                )
                product_image.source_payload = merge_payload(
                    product_image.source_payload,
                    {
                        'linked_from_existing_asset_cache': True,
                        'linked_asset_id': cached_asset.id,
                        'linked_at': now.isoformat(),
                    },
                )
                self.stats.archived += 1
                self.stats.reused_assets += 1
                self.stats.relinked_from_cache += 1
                return

        try:
            archived = await asyncio.to_thread(download_and_archive_image, product_image.source_url, requests_session)
        except Exception as exc:
            product_image.resolved_url = resolved_url or product_image.resolved_url
            product_image.sync_status = 'failed'
            product_image.download_attempts = int(product_image.download_attempts or 0) + 1
            product_image.last_downloaded_at = now
            product_image.sync_message = str(exc)[:1000]
            product_image.source_payload = merge_payload(
                product_image.source_payload,
                {
                    'archive_failed_at': now.isoformat(),
                    'archive_error': str(exc)[:1000],
                    'archive_backend': settings.image_archive_backend,
                },
            )
            self.stats.failed += 1
            return

        asset = await session.scalar(select(ImageAsset).where(ImageAsset.sha256 == archived.sha256))
        if asset is None:
            asset = ImageAsset(
                sha256=archived.sha256,
                storage_backend=settings.image_archive_backend,
                storage_bucket=settings.image_archive_bucket,
                storage_key=archived.storage_key,
                file_ext=archived.file_ext,
                mime_type=archived.mime_type,
                width=archived.width,
                height=archived.height,
                file_size=archived.file_size,
                phash=archived.phash,
                dhash=archived.dhash,
                source_url=product_image.source_url,
                resolved_url=archived.resolved_url,
                archive_status='ready',
                archived_at=now,
                source_payload={
                    'archive_backend': settings.image_archive_backend,
                    'archive_bucket': settings.image_archive_bucket,
                    'created_from_product_image_id': product_image.id,
                    'created_at': now.isoformat(),
                },
            )
            session.add(asset)
            await session.flush()
            self.stats.created_assets += 1
        else:
            asset.storage_backend = asset.storage_backend or settings.image_archive_backend
            asset.storage_bucket = asset.storage_bucket or settings.image_archive_bucket
            asset.storage_key = asset.storage_key or archived.storage_key
            asset.file_ext = asset.file_ext or archived.file_ext
            asset.mime_type = asset.mime_type or archived.mime_type
            asset.width = asset.width or archived.width
            asset.height = asset.height or archived.height
            asset.file_size = asset.file_size or archived.file_size
            asset.phash = asset.phash or archived.phash
            asset.dhash = asset.dhash or archived.dhash
            asset.source_url = asset.source_url or product_image.source_url
            asset.resolved_url = asset.resolved_url or archived.resolved_url
            asset.archive_status = 'ready'
            asset.archived_at = asset.archived_at or now
            asset.source_payload = merge_payload(
                asset.source_payload,
                {
                    'last_reused_by_product_image_id': product_image.id,
                    'last_reused_at': now.isoformat(),
                },
            )
            self.stats.reused_assets += 1

        self.source_asset_cache[product_image.source_url] = asset.id
        if archived.resolved_url:
            self.resolved_asset_cache[archived.resolved_url] = asset.id

        self.apply_asset_to_product_image(
            product_image=product_image,
            asset=asset,
            now=now,
            sync_message='archived_to_local_fs',
            resolved_url_override=archived.resolved_url,
            increment_download_attempts=True,
        )
        product_image.source_payload = merge_payload(
            product_image.source_payload,
            {
                'archive_backend': settings.image_archive_backend,
                'archive_bucket': settings.image_archive_bucket,
                'resolved_url': archived.resolved_url,
                'storage_key': archived.storage_key,
                'archived_at': now.isoformat(),
            },
        )

        self.stats.archived += 1
        self.stats.bytes_downloaded += archived.file_size

    def apply_asset_to_product_image(
        self,
        *,
        product_image: ProductImage,
        asset: ImageAsset,
        now: datetime,
        sync_message: str,
        resolved_url_override: str | None = None,
        increment_download_attempts: bool = False,
    ) -> None:
        product_image.asset = asset
        product_image.resolved_url = resolved_url_override or asset.resolved_url or product_image.resolved_url
        product_image.storage_key = asset.storage_key
        product_image.mime_type = asset.mime_type
        product_image.width = asset.width
        product_image.height = asset.height
        product_image.file_size = asset.file_size
        product_image.sha256 = asset.sha256
        product_image.phash = asset.phash
        product_image.dhash = asset.dhash
        product_image.sync_status = 'archived'
        if increment_download_attempts:
            product_image.download_attempts = int(product_image.download_attempts or 0) + 1
        product_image.last_downloaded_at = now
        product_image.sync_message = sync_message


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='下载并归档 product_images 到本地存储，并回写 PostgreSQL 元数据。')
    parser.add_argument('--limit', type=int, default=None, help='最多处理多少条 product_images')
    parser.add_argument('--status', action='append', default=list(DEFAULT_STATUSES), help='按 sync_status 过滤，可重复传入')
    parser.add_argument('--force', action='store_true', help='忽略 sync_status 条件，直接按选中范围重跑')
    parser.add_argument('--dry-run', action='store_true', help='只做下载与校验，不提交数据库事务')
    parser.add_argument('--only-missing-asset', action='store_true', help='只处理还未关联 image_assets 的图片')
    parser.add_argument('--commit-every', type=int, default=50, help='每处理多少条提交一次事务')
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    archiver = ProductImageArchiver(
        limit=args.limit,
        statuses=tuple(dict.fromkeys(args.status)),
        force=args.force,
        dry_run=args.dry_run,
        only_missing_asset=args.only_missing_asset,
        commit_every=max(1, args.commit_every),
    )
    await archiver.run()


if __name__ == '__main__':
    asyncio.run(main())
