from __future__ import annotations

import html
import json
import re
from copy import deepcopy
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


def extract_item_image_urls(item: dict[str, Any]) -> list[str]:
    """兼容旧 intro HTML 与新商城抓取的结构化 image_urls。"""
    urls: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        if isinstance(value, dict):
            for key in ('url', 'source_url', 'image_url', 'imageUrl', 'src'):
                if key in value:
                    add(value.get(key))
            return
        text = normalize_text(str(value or ''))
        if not text or text in seen:
            return
        seen.add(text)
        urls.append(text)

    for key in ('primary_image_url', 'image_url', 'imageUrl', 'main_image_url'):
        if item.get(key):
            add(item.get(key))

    raw_urls = item.get('image_urls') or item.get('images') or item.get('imageUrls') or []
    if isinstance(raw_urls, (str, bytes)):
        raw_urls = [raw_urls]
    if isinstance(raw_urls, list):
        for raw_url in raw_urls:
            add(raw_url)

    for url in extract_intro_images(str(item.get('intro') or '')):
        add(url)

    return urls


def to_decimal(value: object) -> Decimal | None:
    if value in (None, ''):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def decimal_to_compare_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.normalize(), 'f') if value == value.normalize() else str(value)


def append_limited(items: list[Any], value: Any, limit: int = 20) -> None:
    if len(items) < limit:
        items.append(value)


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
    unchanged_products: int = 0
    created_variants: int = 0
    updated_variants: int = 0
    unchanged_variants: int = 0
    created_images: int = 0
    updated_image_sets: int = 0
    unchanged_image_sets: int = 0
    stale_images_detected: int = 0
    created_rows: int = 0
    updated_rows: int = 0
    unchanged_rows: int = 0
    retried_rows: int = 0
    failed_rows: int = 0
    skipped_unchanged_writes: int = 0
    created_row_examples: list[dict[str, Any]] = field(default_factory=list)
    updated_row_examples: list[dict[str, Any]] = field(default_factory=list)
    unchanged_row_examples: list[dict[str, Any]] = field(default_factory=list)
    failed_row_examples: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload['diff_summary'] = {
            'created_rows': self.created_rows,
            'updated_rows': self.updated_rows,
            'unchanged_rows': self.unchanged_rows,
            'failed_rows': self.failed_rows,
            'retried_rows': self.retried_rows,
            'skipped_unchanged_writes': self.skipped_unchanged_writes,
            'stale_images_detected': self.stale_images_detected,
        }
        return payload


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
        row_retry_attempts: int = 2,
        skip_unchanged_writes: bool = True,
    ) -> None:
        self.session = session
        self.dry_run = dry_run
        self.limit = limit
        self.source_type = source_type
        self.source_name = source_name
        self.requested_by = requested_by
        self.source_path = (source_path or LEGACY_PRODUCTS_PATH).resolve()
        self.row_retry_attempts = max(1, int(row_retry_attempts or 1))
        self.skip_unchanged_writes = skip_unchanged_writes
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
                row_done = False
                last_error: Exception | None = None
                for attempt in range(1, self.row_retry_attempts + 1):
                    stats_snapshot = deepcopy(self.stats)
                    try:
                        async with self.session.begin_nested():
                            await self.import_one(item)
                        row_done = True
                        break
                    except Exception as exc:
                        self.stats = stats_snapshot
                        last_error = exc
                        self._reset_lookup_caches()
                        if attempt < self.row_retry_attempts:
                            self.stats.retried_rows += 1
                            append_limited(
                                self.stats.warnings,
                                f'row retry {attempt}/{self.row_retry_attempts}: {self._row_example_from_item(item, error=str(exc))}',
                                limit=50,
                            )

                if not row_done:
                    self.stats.failed_rows += 1
                    append_limited(
                        self.stats.failed_row_examples,
                        self._row_example_from_item(item, error=str(last_error or 'unknown error')),
                    )
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
                message=error_message
                or (
                    f'商品库同步完成，处理 {self.stats.processed} 条'
                    f'，新增 {self.stats.created_rows}，更新 {self.stats.updated_rows}'
                    f'，无变化 {self.stats.unchanged_rows}，失败 {self.stats.failed_rows}。'
                ),
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
            'row_retry_attempts': self.row_retry_attempts,
            'skip_unchanged_writes': self.skip_unchanged_writes,
        }

    def _reset_lookup_caches(self) -> None:
        self.brand_cache.clear()
        self.supplier_cache.clear()
        self.category_cache.clear()

    @staticmethod
    def _row_example_from_item(item: dict[str, Any], *, error: str | None = None) -> dict[str, Any]:
        code = normalize_text(str((item or {}).get('code') or ''))
        name = normalize_text(str((item or {}).get('name') or ''))
        example = {
            'code': code[:160] if code else None,
            'name': name[:160] if name else None,
        }
        if error:
            example['error'] = error[:500]
        return example

    async def import_one(self, item: dict[str, Any]) -> None:
        code = normalize_text(str(item.get('code') or ''))
        name = normalize_text(str(item.get('name') or ''))
        if not code or not name:
            self.stats.warnings.append(f'missing code/name: {item}')
            self.stats.failed_rows += 1
            append_limited(
                self.stats.failed_row_examples,
                self._row_example_from_item(item, error='missing code/name'),
            )
            return

        brand = await self.get_or_create_brand(normalize_text(str(item.get('brand') or '')))
        supplier = await self.get_or_create_supplier(normalize_text(str(item.get('supplier') or '')))
        category = await self.get_or_create_category_path(normalize_text(str(item.get('category') or '')))
        status, is_active = map_status(str(item.get('status') or ''))
        intro_text = clean_intro(str(item.get('intro') or ''))
        image_urls = extract_item_image_urls(item)
        model = normalize_text(str(item.get('model') or ''))
        unit = normalize_text(str(item.get('unit') or ''))
        reference_price = to_decimal(item.get('market_price'))
        sale_price = to_decimal(item.get('market_price'))
        cost_price = to_decimal(item.get('cost_price'))
        primary_image_url = image_urls[0] if image_urls else None
        search_text = build_search_text(item)
        image_sync_mode = normalize_text(str(item.get('image_sync_mode') or 'replace')) or 'replace'

        product = await self.session.scalar(
            select(Product).where(
                Product.source_type == self.source_type,
                Product.external_product_id == code,
            )
        )

        is_new_product = product is None
        product_changes: list[str] = []
        if product is None:
            product = Product(
                source_type=self.source_type,
                external_product_id=code,
            )
            self.session.add(product)
            self.stats.created_products += 1
        else:
            product_expected = {
                'product_code': code,
                'name': name,
                'normalized_name': name,
                'brand_id': brand.id if brand else None,
                'category_id': category.id if category else None,
                'supplier_id': supplier.id if supplier else None,
                'status': status,
                'is_active': is_active,
                'unit': unit,
                'reference_price': decimal_to_compare_text(reference_price),
                'primary_image_url': primary_image_url,
                'search_text': search_text,
            }
            product_current = {
                'product_code': product.product_code,
                'name': product.name,
                'normalized_name': product.normalized_name,
                'brand_id': product.brand_id,
                'category_id': product.category_id,
                'supplier_id': product.supplier_id,
                'status': product.status,
                'is_active': product.is_active,
                'unit': product.unit,
                'reference_price': decimal_to_compare_text(product.reference_price),
                'primary_image_url': product.primary_image_url,
                'search_text': product.search_text,
            }
            product_changes = [
                field_name
                for field_name, expected_value in product_expected.items()
                if product_current.get(field_name) != expected_value
            ]
            if product_changes:
                self.stats.updated_products += 1
            else:
                self.stats.unchanged_products += 1

        product_should_write = is_new_product or bool(product_changes) or not self.skip_unchanged_writes
        if product_should_write:
            product.product_code = code
            product.name = name
            product.normalized_name = name
            product.brand = brand
            product.category = category
            product.supplier = supplier
            product.status = status
            product.is_active = is_active
            product.unit = unit
            product.reference_price = reference_price
            product.primary_image_url = primary_image_url
            product.search_text = search_text
            product.last_synced_at = datetime.now(timezone.utc)
            product.source_payload = {
                'source_row': item,
                'source_intro_text': intro_text,
                'source_image_count': len(image_urls),
                'source_type': self.source_type,
                'image_sync_mode': image_sync_mode,
                'sync_note': '当前商品源缺少统一 SPU/SKU 拆分，先按一行一个 product + 一个 variant 迁移。',
            }

        if is_new_product:
            await self.session.flush()

        variant = await self.session.scalar(
            select(ProductVariant).where(
                ProductVariant.product_id == product.id,
                ProductVariant.external_variant_id == code,
            )
        )
        is_new_variant = variant is None
        variant_changes: list[str] = []
        if variant is None:
            variant = ProductVariant(
                product_id=product.id,
                external_variant_id=code,
            )
            self.session.add(variant)
            self.stats.created_variants += 1
        else:
            variant_expected = {
                'sku_code': code,
                'variant_name': model or name,
                'spec_text': model,
                'normalized_spec': model,
                'sale_price': decimal_to_compare_text(sale_price),
                'cost_price': decimal_to_compare_text(cost_price),
                'status': status,
                'is_active': is_active,
            }
            variant_current = {
                'sku_code': variant.sku_code,
                'variant_name': variant.variant_name,
                'spec_text': variant.spec_text,
                'normalized_spec': variant.normalized_spec,
                'sale_price': decimal_to_compare_text(variant.sale_price),
                'cost_price': decimal_to_compare_text(variant.cost_price),
                'status': variant.status,
                'is_active': variant.is_active,
            }
            variant_changes = [
                field_name
                for field_name, expected_value in variant_expected.items()
                if variant_current.get(field_name) != expected_value
            ]
            if variant_changes:
                self.stats.updated_variants += 1
            else:
                self.stats.unchanged_variants += 1

        variant_should_write = is_new_variant or bool(variant_changes) or not self.skip_unchanged_writes
        if variant_should_write:
            variant.sku_code = code
            variant.variant_name = model or name
            variant.spec_text = model
            variant.normalized_spec = model
            variant.sale_price = sale_price
            variant.cost_price = cost_price
            variant.status = status
            variant.is_active = is_active
            variant.last_synced_at = datetime.now(timezone.utc)
            variant.source_payload = {
                'source_row_code': code,
                'import_mode': 'one-row-one-variant',
                'source_image_count': len(image_urls),
                'source_type': self.source_type,
                'image_sync_mode': image_sync_mode,
                'is_new_product': is_new_product,
                'is_new_variant': is_new_variant,
            }

        if is_new_variant:
            await self.session.flush()
        image_diff = await self.sync_product_images(product, variant, image_urls, image_sync_mode=image_sync_mode)

        row_example = {'code': code, 'name': name}
        if is_new_product:
            self.stats.created_rows += 1
            append_limited(self.stats.created_row_examples, row_example)
        elif is_new_variant or product_changes or variant_changes or image_diff.get('changed'):
            self.stats.updated_rows += 1
            append_limited(
                self.stats.updated_row_examples,
                {
                    **row_example,
                    'variant_created': is_new_variant,
                    'product_fields': product_changes,
                    'variant_fields': variant_changes,
                    'image_created': image_diff.get('created', 0),
                    'image_stale': image_diff.get('stale', 0),
                },
            )
        else:
            self.stats.unchanged_rows += 1
            if self.skip_unchanged_writes:
                self.stats.skipped_unchanged_writes += 1
            append_limited(self.stats.unchanged_row_examples, row_example)

    async def sync_product_images(
        self,
        product: Product,
        variant: ProductVariant,
        image_urls: list[str],
        *,
        image_sync_mode: str = 'replace',
    ) -> dict[str, Any]:
        existing = await self.session.scalars(
            select(ProductImage)
            .where(
                ProductImage.product_id == product.id,
                ProductImage.variant_id == variant.id,
            )
            .order_by(ProductImage.sort_order.asc(), ProductImage.id.asc())
        )
        existing_items = list(existing)
        existing_urls = [image.source_url for image in existing_items]
        image_sync_mode = normalize_text(str(image_sync_mode or 'replace')) or 'replace'
        incoming_urls = list(image_urls)
        if image_sync_mode == 'append_only':
            existing_url_set = set(existing_urls)
            incoming_urls = existing_urls + [image_url for image_url in image_urls if image_url not in existing_url_set]
        incoming_url_set = set(incoming_urls)
        stale_count = 0 if image_sync_mode == 'append_only' else sum(1 for image_url in existing_urls if image_url not in incoming_url_set)
        changed = existing_urls != incoming_urls

        if existing_urls or incoming_urls:
            if changed:
                self.stats.updated_image_sets += 1
            else:
                self.stats.unchanged_image_sets += 1
        self.stats.stale_images_detected += stale_count

        if not changed and self.skip_unchanged_writes:
            return {
                'changed': False,
                'created': 0,
                'stale': stale_count,
            }

        existing_by_url = {image.source_url: image for image in existing_items}
        created_count = 0

        for index, image_url in enumerate(incoming_urls):
            image = existing_by_url.get(image_url)
            if image is None:
                image = ProductImage(
                    product_id=product.id,
                    variant_id=variant.id,
                    source_url=image_url,
                )
                self.session.add(image)
                self.stats.created_images += 1
                created_count += 1
                image.sync_status = 'pending'

            image.image_role = 'gallery'
            image.sort_order = index
            image.is_primary = index == 0
            image.source_payload = {
                'source_type': self.source_type,
                'source_name': self.source_name,
                'image_sync_mode': image_sync_mode,
                'product_code': product.product_code,
                'variant_code': variant.sku_code,
            }

        return {
            'changed': changed,
            'created': created_count,
            'stale': stale_count,
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
