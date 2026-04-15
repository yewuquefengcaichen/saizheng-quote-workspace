from __future__ import annotations

import html
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Brand, Category, Product, ProductImage, ProductVariant, Supplier, SyncJob, SyncJobLog


LEGACY_PRODUCTS_PATH = Path(__file__).resolve().parents[3] / 'data' / 'products.json'
CATEGORY_SEPARATOR = '\u03be'
IMG_SRC_PATTERN = re.compile(r"""<img[^>]+src=["']([^"']+)["']""", re.IGNORECASE)


def normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = re.sub(r'\s+', ' ', value).strip()
    return value or None


def clean_intro(value: str | None) -> str | None:
    if not value:
        return None
    text = html.unescape(value)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text or None


def extract_intro_images(value: str | None) -> list[str]:
    if not value:
        return []
    intro = html.unescape(value)
    matches = [normalize_text(match) for match in IMG_SRC_PATTERN.findall(intro)]
    deduped: list[str] = []
    seen: set[str] = set()
    for match in matches:
        if not match or match in seen:
            continue
        seen.add(match)
        deduped.append(match)
    return deduped


def to_decimal(value: object) -> Decimal | None:
    if value in (None, ''):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def map_status(raw_status: str | None) -> tuple[str, bool]:
    normalized = normalize_text(raw_status)
    if normalized == '上架':
        return 'active', True
    if normalized == '下架':
        return 'inactive', False
    return 'unknown', False


def build_search_text(item: dict[str, Any]) -> str:
    parts = [
        normalize_text(str(item.get('name') or '')),
        normalize_text(str(item.get('model') or '')),
        normalize_text(str(item.get('brand') or '')),
        normalize_text(str(item.get('supplier') or '')),
        normalize_text(str(item.get('category') or '')),
        clean_intro(str(item.get('intro') or '')),
    ]
    return ' | '.join(part for part in parts if part)


@dataclass
class CatalogSyncStats:
    processed: int = 0
    created_brands: int = 0
    created_categories: int = 0
    created_suppliers: int = 0
    created_products: int = 0
    updated_products: int = 0
    created_variants: int = 0
    updated_variants: int = 0
    created_images: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_sync_job_summary(job: SyncJob | None) -> dict[str, Any]:
    if job is None:
        return {
            'exists': False,
            'status': 'idle',
            'job_type': 'catalog_manual_sync',
        }

    return {
        'exists': True,
        'job_id': job.id,
        'public_id': job.public_id,
        'job_type': job.job_type,
        'source_name': job.source_name,
        'trigger_mode': job.trigger_mode,
        'status': job.status,
        'requested_by': job.requested_by,
        'total_steps': job.total_steps,
        'completed_steps': job.completed_steps,
        'stats': job.stats_json or {},
        'error_message': job.error_message,
        'started_at': job.started_at.isoformat() if job.started_at else None,
        'finished_at': job.finished_at.isoformat() if job.finished_at else None,
        'updated_at': job.updated_at.isoformat() if job.updated_at else None,
    }


async def get_latest_catalog_sync_job(session: AsyncSession) -> SyncJob | None:
    return await session.scalar(
        select(SyncJob)
        .where(SyncJob.job_type == 'catalog_manual_sync')
        .order_by(SyncJob.created_at.desc(), SyncJob.id.desc())
        .limit(1)
    )


class LegacyCatalogSyncService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        dry_run: bool = False,
        limit: int | None = None,
        source_type: str = 'legacy_json_upload',
        source_name: str = 'products_json_manual',
        requested_by: str | None = None,
        source_path: Path | None = None,
    ) -> None:
        self.session = session
        self.dry_run = dry_run
        self.limit = limit
        self.source_type = source_type
        self.source_name = source_name
        self.requested_by = requested_by
        self.source_path = (source_path or LEGACY_PRODUCTS_PATH).resolve()
        self.brand_cache: dict[str, Brand] = {}
        self.supplier_cache: dict[str, Supplier] = {}
        self.category_cache: dict[tuple[str, ...], Category] = {}
        self.stats = CatalogSyncStats()
        self.job: SyncJob | None = None
        self.job_id: int | None = None

    async def run_from_default_file(self) -> dict[str, Any]:
        if not self.source_path.exists():
            raise FileNotFoundError(f'找不到商品源文件: {self.source_path}')

        items = json.loads(self.source_path.read_text(encoding='utf-8'))
        if not isinstance(items, list):
            raise ValueError('商品源文件格式错误，期望为 JSON 数组')

        if self.limit is not None:
            items = items[: self.limit]

        return await self.run_items(items)

    async def run_items(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.dry_run:
            await self._start_job(len(items))

        try:
            for index, item in enumerate(items, start=1):
                await self.import_one(item)
                self.stats.processed += 1

                if index % 300 == 0:
                    await self.session.flush()
                    if self.job is not None:
                        self.job.completed_steps = index
                        self.job.stats_json = self._build_job_stats_payload()
                        await self.session.flush()

            if self.dry_run:
                await self.session.rollback()
                return {
                    'dry_run': True,
                    'stats': self.stats.to_dict(),
                    'job': None,
                }

            await self.session.commit()
            await self._finish_job(status='success')
            return {
                'dry_run': False,
                'stats': self.stats.to_dict(),
                'job': build_sync_job_summary(self.job),
            }
        except Exception as exc:
            await self.session.rollback()
            if self.job is not None and not self.dry_run:
                await self._finish_job(status='failed', error_message=str(exc))
            raise

    async def _start_job(self, total_steps: int) -> None:
        started_at = datetime.now(timezone.utc)
        self.job = SyncJob(
            job_type='catalog_manual_sync',
            source_name=self.source_name,
            trigger_mode='manual',
            status='running',
            requested_by=self.requested_by,
            total_steps=total_steps,
            completed_steps=0,
            started_at=started_at,
            stats_json={
                'source_path': str(self.source_path),
                'dry_run': False,
                'source_type': self.source_type,
            },
        )
        self.session.add(self.job)
        await self.session.flush()
        self.session.add(
            SyncJobLog(
                job_id=self.job.id,
                level='info',
                event_type='job_started',
                message=f'开始同步商品库，共 {total_steps} 条。',
                context_json={
                    'source_path': str(self.source_path),
                    'source_type': self.source_type,
                },
            )
        )
        await self.session.commit()
        await self.session.refresh(self.job)
        self.job_id = int(self.job.id)

    async def _finish_job(self, *, status: str, error_message: str | None = None) -> None:
        if self.job_id is None:
            return

        stats_payload = self._build_job_stats_payload()
        await self.session.execute(
            update(SyncJob)
            .where(SyncJob.id == self.job_id)
            .values(
                status=status,
                completed_steps=self.stats.processed,
                finished_at=datetime.now(timezone.utc),
                error_message=error_message,
                stats_json=stats_payload,
            )
        )
        self.session.add(
            SyncJobLog(
                job_id=self.job_id,
                level='error' if error_message else 'info',
                event_type='job_finished',
                message=error_message or f'商品库同步完成，处理 {self.stats.processed} 条。',
                context_json=stats_payload,
            )
        )
        await self.session.commit()
        self.job = await self.session.scalar(select(SyncJob).where(SyncJob.id == self.job_id))

    def _build_job_stats_payload(self) -> dict[str, Any]:
        return {
            **self.stats.to_dict(),
            'source_path': str(self.source_path),
            'source_type': self.source_type,
        }

    async def import_one(self, item: dict[str, Any]) -> None:
        code = normalize_text(str(item.get('code') or ''))
        name = normalize_text(str(item.get('name') or ''))
        if not code or not name:
            self.stats.warnings.append(f'missing code/name: {item}')
            return

        brand = await self.get_or_create_brand(normalize_text(str(item.get('brand') or '')))
        supplier = await self.get_or_create_supplier(normalize_text(str(item.get('supplier') or '')))
        category = await self.get_or_create_category_path(normalize_text(str(item.get('category') or '')))
        status, is_active = map_status(str(item.get('status') or ''))
        intro_text = clean_intro(str(item.get('intro') or ''))
        image_urls = extract_intro_images(str(item.get('intro') or ''))

        product = await self.session.scalar(
            select(Product).where(
                Product.source_type == self.source_type,
                Product.external_product_id == code,
            )
        )

        is_new_product = product is None
        if product is None:
            product = Product(
                source_type=self.source_type,
                external_product_id=code,
            )
            self.session.add(product)
            self.stats.created_products += 1
        else:
            self.stats.updated_products += 1

        product.product_code = code
        product.name = name
        product.normalized_name = name
        product.brand = brand
        product.category = category
        product.supplier = supplier
        product.status = status
        product.is_active = is_active
        product.unit = normalize_text(str(item.get('unit') or ''))
        product.reference_price = to_decimal(item.get('market_price'))
        product.primary_image_url = image_urls[0] if image_urls else None
        product.search_text = build_search_text(item)
        product.last_synced_at = datetime.now(timezone.utc)
        product.source_payload = {
            'legacy_row': item,
            'legacy_intro_text': intro_text,
            'legacy_image_count': len(image_urls),
            'legacy_note': '当前旧商品库缺少明确 SPU/SKU 拆分，先按一行一个 product + 一个 variant 迁移。',
        }

        await self.session.flush()

        variant = await self.session.scalar(
            select(ProductVariant).where(
                ProductVariant.product_id == product.id,
                ProductVariant.external_variant_id == code,
            )
        )
        if variant is None:
            variant = ProductVariant(
                product_id=product.id,
                external_variant_id=code,
            )
            self.session.add(variant)
            self.stats.created_variants += 1
        else:
            self.stats.updated_variants += 1

        variant.sku_code = code
        variant.variant_name = normalize_text(str(item.get('model') or '')) or name
        variant.spec_text = normalize_text(str(item.get('model') or ''))
        variant.normalized_spec = normalize_text(str(item.get('model') or ''))
        variant.sale_price = to_decimal(item.get('market_price'))
        variant.cost_price = to_decimal(item.get('cost_price'))
        variant.status = status
        variant.is_active = is_active
        variant.last_synced_at = datetime.now(timezone.utc)
        variant.source_payload = {
            'legacy_row_code': code,
            'import_mode': 'one-row-one-variant',
            'legacy_image_count': len(image_urls),
            'is_new_product': is_new_product,
        }

        await self.sync_product_images(product, variant, image_urls)

    async def sync_product_images(self, product: Product, variant: ProductVariant, image_urls: list[str]) -> None:
        if not image_urls:
            return

        existing = await self.session.scalars(
            select(ProductImage).where(
                ProductImage.product_id == product.id,
                ProductImage.variant_id == variant.id,
            )
        )
        existing_by_url = {image.source_url: image for image in existing}

        for index, image_url in enumerate(image_urls):
            image = existing_by_url.get(image_url)
            if image is None:
                image = ProductImage(
                    product_id=product.id,
                    variant_id=variant.id,
                    source_url=image_url,
                )
                self.session.add(image)
                self.stats.created_images += 1

            image.image_role = 'gallery'
            image.sort_order = index
            image.is_primary = index == 0
            image.sync_status = 'pending'
            image.source_payload = {
                'legacy_source': 'products.json:intro',
                'legacy_product_code': product.product_code,
                'legacy_variant_code': variant.sku_code,
            }

    async def get_or_create_brand(self, name: str | None) -> Brand | None:
        if not name:
            return None
        if name in self.brand_cache:
            return self.brand_cache[name]

        brand = await self.session.scalar(select(Brand).where(Brand.name == name))
        if brand is None:
            brand = Brand(name=name, normalized_name=name)
            self.session.add(brand)
            await self.session.flush()
            self.stats.created_brands += 1

        self.brand_cache[name] = brand
        return brand

    async def get_or_create_supplier(self, name: str | None) -> Supplier | None:
        if not name:
            return None
        if name in self.supplier_cache:
            return self.supplier_cache[name]

        supplier = await self.session.scalar(select(Supplier).where(Supplier.name == name))
        if supplier is None:
            supplier = Supplier(name=name, normalized_name=name)
            self.session.add(supplier)
            await self.session.flush()
            self.stats.created_suppliers += 1

        self.supplier_cache[name] = supplier
        return supplier

    async def get_or_create_category_path(self, category_path: str | None) -> Category | None:
        if not category_path:
            return None

        parts = tuple(part.strip() for part in category_path.split(CATEGORY_SEPARATOR) if part.strip())
        if not parts:
            return None
        if parts in self.category_cache:
            return self.category_cache[parts]

        parent: Category | None = None
        seen_parts: list[str] = []
        for part in parts:
            seen_parts.append(part)
            cache_key = tuple(seen_parts)
            if cache_key in self.category_cache:
                parent = self.category_cache[cache_key]
                continue

            stmt = select(Category).where(Category.name == part)
            if parent is None:
                stmt = stmt.where(Category.parent_id.is_(None))
            else:
                stmt = stmt.where(Category.parent_id == parent.id)

            category = await self.session.scalar(stmt)
            if category is None:
                category = Category(
                    name=part,
                    normalized_name=part,
                    parent=parent,
                    level=len(seen_parts),
                    path=CATEGORY_SEPARATOR.join(seen_parts),
                )
                self.session.add(category)
                await self.session.flush()
                self.stats.created_categories += 1

            self.category_cache[cache_key] = category
            parent = category

        return parent
