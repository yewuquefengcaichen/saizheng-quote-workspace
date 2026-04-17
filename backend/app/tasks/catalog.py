from __future__ import annotations

import asyncio
from typing import Any

from app.core.celery_app import celery_app
from app.services.mall_sync import pick_mall_scrape_options, run_mall_scrape_sync_async


@celery_app.task(name='app.tasks.catalog.scrape_mall_sync', bind=True)
def scrape_mall_sync_task(
    self,
    requested_by: str = 'catalog-page-mall-scrape',
    options: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    safe_options = pick_mall_scrape_options(options)
    return asyncio.run(
        run_mall_scrape_sync_async(
            requested_by=requested_by,
            options=safe_options,
            dry_run=bool(dry_run),
        )
    )
