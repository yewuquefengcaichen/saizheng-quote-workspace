from __future__ import annotations

import argparse
import asyncio
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models import MatchFeedback, Product, ProductVariant, QuoteBatch, QuoteItem  # noqa: E402

LEGACY_DB_PATH = BACKEND_ROOT.parent / 'data' / 'quote_history.db'


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def to_decimal(value: Any) -> Decimal | None:
    if value in (None, ''):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


@dataclass
class HistoryImportStats:
    quote_batches_created: int = 0
    quote_batches_updated: int = 0
    quote_items_created: int = 0
    quote_items_updated: int = 0
    match_feedback_created: int = 0
    match_feedback_updated: int = 0


class LegacyHistoryImporter:
    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self.stats = HistoryImportStats()

    async def run(self) -> None:
        conn = sqlite3.connect(LEGACY_DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            async with AsyncSessionLocal() as session:
                await self.import_quote_history(session, conn)
                await self.import_match_feedback(session, conn)

                if self.dry_run:
                    await session.rollback()
                    print('[legacy-history] dry-run complete, transaction rolled back')
                else:
                    await session.commit()
                    print('[legacy-history] import committed')
        finally:
            conn.close()

        print(self.stats)

    async def import_quote_history(self, session, conn: sqlite3.Connection) -> None:
        history_rows = conn.execute('SELECT * FROM quote_history ORDER BY id').fetchall()
        for history in history_rows:
            source_filename = f'legacy_quote_history_{history["id"]}'
            batch = await session.scalar(
                select(QuoteBatch).where(
                    QuoteBatch.source_type == 'legacy_history',
                    QuoteBatch.source_filename == source_filename,
                )
            )
            if batch is None:
                batch = QuoteBatch(source_type='legacy_history', source_filename=source_filename)
                session.add(batch)
                self.stats.quote_batches_created += 1
            else:
                self.stats.quote_batches_updated += 1

            batch.import_status = 'completed'
            batch.parse_status = 'completed'
            batch.total_items = int(history['total_items'] or 0)
            batch.confirmed_items = int(history['matched_items'] or 0)
            batch.unmatched_items = max(batch.total_items - batch.confirmed_items, 0)
            batch.imported_at = parse_datetime(history['created_at'])
            batch.parsed_at = parse_datetime(history['created_at'])
            batch.source_payload = {
                'legacy_quote_history_id': history['id'],
                'customer_name': history['customer_name'],
                'quote_file': history['quote_file'],
                'total_amount': history['total_amount'],
                'export_file': history['export_file'],
                'remark': history['remark'],
            }

            await session.flush()

            item_rows = conn.execute('SELECT * FROM quote_items WHERE quote_id = ? ORDER BY id', (history['id'],)).fetchall()
            for row_number, item in enumerate(item_rows, start=1):
                quote_item = await session.scalar(
                    select(QuoteItem).where(
                        QuoteItem.batch_id == batch.id,
                        QuoteItem.row_number == row_number,
                    )
                )
                if quote_item is None:
                    quote_item = QuoteItem(batch_id=batch.id, row_number=row_number, raw_name=item['item_name'])
                    session.add(quote_item)
                    self.stats.quote_items_created += 1
                else:
                    self.stats.quote_items_updated += 1

                product = await session.scalar(select(Product).where(Product.product_code == item['product_code']))
                variant = await session.scalar(select(ProductVariant).where(ProductVariant.sku_code == item['product_code']))

                quote_item.raw_name = item['item_name']
                quote_item.raw_spec = None
                quote_item.raw_brand = None
                quote_item.raw_model = None
                quote_item.quantity = to_decimal(item['item_quantity'])
                quote_item.unit = item['item_unit']
                quote_item.target_price = to_decimal(item['budget_price']) or to_decimal(item['item_price'])
                quote_item.normalized_name = item['item_name']
                quote_item.selected_product_id = product.id if product else None
                quote_item.selected_variant_id = variant.id if variant else None
                quote_item.match_status = 'matched' if item['product_code'] else 'pending'
                quote_item.quote_status = 'confirmed' if item['product_code'] else 'unconfirmed'
                quote_item.note = None
                quote_item.source_payload = {
                    'legacy_quote_item_id': item['id'],
                    'legacy_quote_id': item['quote_id'],
                    'legacy_product_name': item['product_name'],
                    'legacy_supplier': item['supplier'],
                    'legacy_item_price': item['item_price'],
                    'legacy_match_score': item['match_score'],
                }

    async def import_match_feedback(self, session, conn: sqlite3.Connection) -> None:
        rows = conn.execute('SELECT * FROM match_feedback ORDER BY id').fetchall()
        for row in rows:
            created_at = parse_datetime(row['created_at'])
            feedback = await session.scalar(
                select(MatchFeedback).where(
                    MatchFeedback.created_at == created_at,
                    MatchFeedback.query_signature == row['query_signature'],
                    MatchFeedback.selected_product_code == row['selected_product_code'],
                    MatchFeedback.action == row['action'],
                )
            )
            if feedback is None:
                feedback = MatchFeedback()
                session.add(feedback)
                self.stats.match_feedback_created += 1
            else:
                self.stats.match_feedback_updated += 1

            feedback.created_at = created_at
            feedback.source_type = row['source_type']
            feedback.template_name = row['template_name']
            feedback.template_hit = bool(row['template_hit'])
            feedback.action = row['action']
            feedback.original_name = row['original_name']
            feedback.original_spec = row['original_spec']
            feedback.original_unit = row['original_unit']
            feedback.normalized_name = row['normalized_name']
            feedback.normalized_spec = row['normalized_spec']
            feedback.normalized_unit = row['normalized_unit']
            feedback.selected_product_code = row['selected_product_code']
            feedback.selected_product_name = row['selected_product_name']
            feedback.top_candidate_code = row['top_candidate_code']
            feedback.top_candidate_name = row['top_candidate_name']
            feedback.top_candidate_score = to_decimal(row['top_candidate_score'])
            feedback.top_candidate_rank = row['top_candidate_rank']
            feedback.selected_rank = row['selected_rank']
            feedback.selected_score = to_decimal(row['selected_score'])
            feedback.with_product_image = bool(row['with_product_image'])
            feedback.ocr_confidence = to_decimal(row['ocr_confidence'])
            feedback.query_signature = row['query_signature']
            feedback.feedback_weight = to_decimal(row['feedback_weight'])
            feedback.mapping_signature = row['mapping_signature']
            feedback.mapping_changed = bool(row['mapping_changed'])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Import legacy quote history and match feedback into PostgreSQL V2 schema')
    parser.add_argument('--dry-run', action='store_true', help='Run import but rollback at the end')
    return parser.parse_args()


async def async_main() -> None:
    args = parse_args()
    importer = LegacyHistoryImporter(dry_run=args.dry_run)
    await importer.run()


if __name__ == '__main__':
    asyncio.run(async_main())
