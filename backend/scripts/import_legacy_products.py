from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.services.catalog_sync import LegacyCatalogSyncService  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Import legacy products.json into PostgreSQL V2 schema')
    parser.add_argument('--dry-run', action='store_true', help='Run import but rollback at the end')
    parser.add_argument('--limit', type=int, default=None, help='Only process the first N rows')
    parser.add_argument('--source-type', default='legacy_json_upload', help='source_type stored in products table')
    parser.add_argument('--source-name', default='products_json_manual', help='source_name stored in sync_jobs table')
    parser.add_argument('--requested-by', default='manual-script', help='operator name recorded in sync_jobs table')
    return parser.parse_args()


async def async_main() -> None:
    args = parse_args()
    async with AsyncSessionLocal() as session:
        service = LegacyCatalogSyncService(
            session,
            dry_run=args.dry_run,
            limit=args.limit,
            source_type=args.source_type,
            source_name=args.source_name,
            requested_by=args.requested_by,
        )
        result = await service.run_from_default_file()
        print(result)


if __name__ == '__main__':
    asyncio.run(async_main())
