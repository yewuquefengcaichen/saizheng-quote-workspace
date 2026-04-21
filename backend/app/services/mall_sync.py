from __future__ import annotations

from pathlib import Path
from typing import Any

from app.db.session import AsyncSessionLocal
from app.services.catalog_sync import LegacyCatalogSyncService
from app.services.mall_scraper import MallPlaywrightScraper, build_default_mall_scrape_config


MALL_SCRAPE_OPTION_KEYS = (
    'start_url',
    'page_url_template',
    'max_pages',
    'start_page',
    'max_items',
    'headless',
    'storage_state_path',
    'page_timeout_ms',
    'page_delay_ms',
    'next_delay_ms',
    'detail_delay_ms',
    'product_card_selector',
    'next_selector',
    'checkpoint_path',
    'resume_from_checkpoint',
    'network_include_patterns',
    'network_exclude_patterns',
    'dom_table_selector',
    'site_adapter',
    'fetch_detail_images',
    'detail_fetch_limit',
    'detail_image_limit_per_item',
    'field_map',
    'screenshot_path',
)


def pick_mall_scrape_options(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    return {key: payload[key] for key in MALL_SCRAPE_OPTION_KEYS if key in payload}


async def run_mall_scrape_sync_async(
    *,
    requested_by: str = 'mall-scrape',
    options: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    scrape_config = build_default_mall_scrape_config(**pick_mall_scrape_options(options))
    scraper = MallPlaywrightScraper(scrape_config)
    scrape_result = await scraper.scrape()

    async with AsyncSessionLocal() as session:
        service = LegacyCatalogSyncService(
            session,
            dry_run=dry_run,
            source_type='legacy_json_upload',
            source_name='mall_playwright_scrape',
            requested_by=requested_by,
            source_path=Path('mall_playwright_scrape'),
        )
        sync_result = await service.run_items(scrape_result.items)

    return {
        **sync_result,
        'scrape': {
            'stats': scrape_result.stats.to_dict(),
            'visited_urls': scrape_result.visited_urls,
            'sample_items': [
                {
                    **{
                        key: item.get(key)
                        for key in (
                            'code',
                            'name',
                            'model',
                            'category',
                            'unit',
                            'market_price',
                            'cost_price',
                            'brand',
                            'supplier',
                            'status',
                            'primary_image_url',
                            'detail_url',
                            'detail_image_count',
                        )
                    },
                    'image_count': len(item.get('image_urls') or []),
                }
                for item in scrape_result.items[:10]
            ],
            'raw_payload_examples': scrape_result.raw_payload_examples,
            'config': {
                'start_url': scrape_config.start_url,
                'page_url_template': scrape_config.page_url_template,
                'max_pages': scrape_config.max_pages,
                'start_page': scrape_config.start_page,
                'max_items': scrape_config.max_items,
                'headless': scrape_config.headless,
                'page_timeout_ms': scrape_config.page_timeout_ms,
                'page_delay_ms': scrape_config.page_delay_ms,
                'next_delay_ms': scrape_config.next_delay_ms,
                'detail_delay_ms': scrape_config.detail_delay_ms,
                'product_card_selector': scrape_config.product_card_selector,
                'next_selector': scrape_config.next_selector,
                'checkpoint_configured': bool(scrape_config.checkpoint_path),
                'resume_from_checkpoint': scrape_config.resume_from_checkpoint,
                'dom_table_selector': scrape_config.dom_table_selector,
                'site_adapter': scrape_config.site_adapter,
                'fetch_detail_images': scrape_config.fetch_detail_images,
                'detail_fetch_limit': scrape_config.detail_fetch_limit,
                'detail_image_limit_per_item': scrape_config.detail_image_limit_per_item,
                'network_include_patterns': scrape_config.network_include_patterns,
                'network_exclude_patterns': scrape_config.network_exclude_patterns,
                'storage_state_configured': bool(scrape_config.storage_state_path),
            },
        },
    }
