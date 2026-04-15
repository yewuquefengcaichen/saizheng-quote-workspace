from __future__ import annotations

import argparse
import asyncio
import html
import json
import re
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models import Brand, Category, Product, ProductImage, ProductVariant, Supplier  # noqa: E402


LEGACY_PRODUCTS_PATH = BACKEND_ROOT.parent / 'data' / 'products.json'
CATEGORY_SEPARATOR = '\u03be'
IMG_SRC_PATTERN = re.compile(r'''<img[^>]+src=["\']([^"\']+)["\']''', re.IGNORECASE)


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


def build_search_text(item: dict[str, object]) -> str:
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
class ImportStats:
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


class LegacyCatalogImporter:
    def __init__(self, dry_run: bool = False, limit: int | None = None, source_type: str = 'legacy_json_upload') -> None:
        self.dry_run = dry_run
        self.limit = limit
        self.source_type = source_type
        self.brand_cache: dict[str, Brand] = {}
        self.supplier_cache: dict[str, Supplier] = {}
        self.category_cache: dict[tuple[str, ...], Category] = {}
        self.stats = ImportStats()

    async def run(self) -> None:
        items = json.loads(LEGACY_PRODUCTS_PATH.read_text(encoding='utf-8'))
        if self.limit is not None:
            items = items[: self.limit]

        async with AsyncSessionLocal() as session:
            for index, item in enumerate(items, start=1):
                await self.import_one(session, item)
                self.stats.processed += 1
                if index % 300 == 0:
                    await session.flush()
                    print(f'[legacy-import] processed={index}')

            if self.dry_run:
                await session.rollback()
                print('[legacy-import] dry-run complete, transaction rolled back')
            else:
                await session.commit()
                print('[legacy-import] import committed')

        print(self.stats)

    async def import_one(self, session, item: dict[str, object]) -> None:
        code = normalize_text(str(item.get('code') or ''))
        name = normalize_text(str(item.get('name') or ''))
        if not code or not name:
            self.stats.warnings.append(f'missing code/name: {item}')
            return

        brand = await self.get_or_create_brand(session, normalize_text(str(item.get('brand') or '')))
        supplier = await self.get_or_create_supplier(session, normalize_text(str(item.get('supplier') or '')))
        category = await self.get_or_create_category_path(session, normalize_text(str(item.get('category') or '')))
        status, is_active = map_status(str(item.get('status') or ''))
        intro_text = clean_intro(str(item.get('intro') or ''))
        image_urls = extract_intro_images(str(item.get('intro') or ''))

        product = await session.scalar(
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
            session.add(product)
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
        product.source_payload = {
            'legacy_row': item,
            'legacy_intro_text': intro_text,
            'legacy_image_count': len(image_urls),
            'legacy_note': '当前旧商品库缺少明确 SPU/SKU 拆分，先按一行一个 product + 一个 variant 迁移。',
        }

        await session.flush()

        variant = await session.scalar(
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
            session.add(variant)
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
        variant.source_payload = {
            'legacy_row_code': code,
            'import_mode': 'one-row-one-variant',
            'legacy_image_count': len(image_urls),
            'is_new_product': is_new_product,
        }

        await self.sync_product_images(session, product, variant, image_urls)

    async def sync_product_images(self, session, product: Product, variant: ProductVariant, image_urls: list[str]) -> None:
        if not image_urls:
            return

        existing = await session.scalars(
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
                session.add(image)
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

    async def get_or_create_brand(self, session, name: str | None) -> Brand | None:
        if not name:
            return None
        if name in self.brand_cache:
            return self.brand_cache[name]

        brand = await session.scalar(select(Brand).where(Brand.name == name))
        if brand is None:
            brand = Brand(name=name, normalized_name=name)
            session.add(brand)
            await session.flush()
            self.stats.created_brands += 1

        self.brand_cache[name] = brand
        return brand

    async def get_or_create_supplier(self, session, name: str | None) -> Supplier | None:
        if not name:
            return None
        if name in self.supplier_cache:
            return self.supplier_cache[name]

        supplier = await session.scalar(select(Supplier).where(Supplier.name == name))
        if supplier is None:
            supplier = Supplier(name=name, normalized_name=name)
            session.add(supplier)
            await session.flush()
            self.stats.created_suppliers += 1

        self.supplier_cache[name] = supplier
        return supplier

    async def get_or_create_category_path(self, session, category_path: str | None) -> Category | None:
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

            category = await session.scalar(stmt)
            if category is None:
                category = Category(
                    name=part,
                    normalized_name=part,
                    parent=parent,
                    level=len(seen_parts),
                    path=CATEGORY_SEPARATOR.join(seen_parts),
                )
                session.add(category)
                await session.flush()
                self.stats.created_categories += 1

            self.category_cache[cache_key] = category
            parent = category

        return parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Import legacy products.json into PostgreSQL V2 schema')
    parser.add_argument('--dry-run', action='store_true', help='Run import but rollback at the end')
    parser.add_argument('--limit', type=int, default=None, help='Only process the first N rows')
    parser.add_argument('--source-type', default='legacy_json_upload', help='source_type stored in products table')
    return parser.parse_args()


async def async_main() -> None:
    args = parse_args()
    importer = LegacyCatalogImporter(
        dry_run=args.dry_run,
        limit=args.limit,
        source_type=args.source_type,
    )
    await importer.run()


if __name__ == '__main__':
    asyncio.run(async_main())
