from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models import SyncJob, SyncJobLog
from app.services.catalog_sync import LegacyCatalogSyncService
from app.services.mall_scraper import MallPlaywrightScraper, MallScrapeResult, build_default_mall_scrape_config


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
    'crawl_mode',
    'finalize_missing',
    'missing_mark_threshold',
    'rerun_urls',
    'failed_page_urls',
    'rerun_failed_page_urls',
)


def pick_mall_scrape_options(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    return {key: payload[key] for key in MALL_SCRAPE_OPTION_KEYS if key in payload}


async def get_recent_mall_sync_job_summaries(limit: int = 5) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 5), 20))
    async with AsyncSessionLocal() as session:
        jobs = list(
            await session.scalars(
                select(SyncJob)
                .where(SyncJob.job_type == 'catalog_mall_scrape_sync')
                .order_by(SyncJob.created_at.desc(), SyncJob.id.desc())
                .limit(limit)
            )
        )
    return [_build_mall_job_brief(job) for job in jobs]


def _build_mall_job_brief(job: SyncJob) -> dict[str, Any]:
    stats = dict(job.stats_json or {})
    scrape = stats.get('scrape') or {}
    scrape_stats = scrape.get('stats') or {}
    page_records = stats.get('page_records') or scrape_stats.get('page_records') or []
    failed_pages = stats.get('failed_pages') or scrape_stats.get('failed_pages') or []
    diff_summary = stats.get('diff_summary') or {}
    mall_batch = stats.get('mall_batch') or {}
    compact_stats = {
        'mall_batch': mall_batch,
        'diff_summary': diff_summary,
        'scrape': {
            'stats': {
                **scrape_stats,
                'page_records': page_records[:5],
                'failed_pages': failed_pages[:5],
            }
        },
        'page_records': page_records[:5],
        'failed_pages': failed_pages[:5],
    }
    return {
        'job_id': job.id,
        'public_id': job.public_id,
        'status': job.status,
        'requested_by': job.requested_by,
        'started_at': job.started_at.isoformat() if job.started_at else None,
        'finished_at': job.finished_at.isoformat() if job.finished_at else None,
        'updated_at': job.updated_at.isoformat() if job.updated_at else None,
        'error_message': job.error_message,
        'mall_batch': mall_batch,
        'diff_summary': diff_summary,
        'stats': compact_stats,
        'page_summary': {
            'pages_visited': scrape_stats.get('pages_visited', 0),
            'extracted_items': scrape_stats.get('extracted_items', 0),
            'page_records_count': len(page_records),
            'failed_pages_count': len(failed_pages),
            'page_records': page_records[:5],
            'failed_pages': failed_pages[:5],
        },
    }


async def run_mall_scrape_sync_async(
    *,
    requested_by: str = 'mall-scrape',
    options: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    safe_options = pick_mall_scrape_options(options)
    crawl_mode = str(safe_options.get('crawl_mode') or '').strip() or 'small'
    rerun_urls = safe_options.get('rerun_urls') or safe_options.get('failed_page_urls') or safe_options.get('rerun_failed_page_urls') or []
    if isinstance(rerun_urls, (str, bytes)):
        rerun_urls = [str(rerun_urls)]
    rerun_urls = [str(url).strip() for url in rerun_urls if str(url or '').strip()]
    rerun_failed_pages = bool(rerun_urls)
    if rerun_failed_pages and crawl_mode == 'small':
        crawl_mode = 'rerun_failed_pages'
    batch_id = f'mall-{datetime.now(timezone.utc):%Y%m%d%H%M%S}-{uuid4().hex[:8]}'
    batch_started_at = datetime.now(timezone.utc).isoformat()
    finalize_missing = (
        not dry_run
        and crawl_mode == 'full'
        and bool(safe_options.get('finalize_missing', True))
    )
    try:
        missing_mark_threshold = int(safe_options.get('missing_mark_threshold') or 3)
    except Exception:
        missing_mark_threshold = 3

    scrape_config = build_default_mall_scrape_config(**safe_options)
    scraper = MallPlaywrightScraper(scrape_config)
    scrape_result = await scraper.scrape()

    mall_batch = {
        'batch_id': batch_id,
        'crawl_mode': crawl_mode,
        'started_at': batch_started_at,
        'checkpoint_path': scrape_config.checkpoint_path,
        'resume_from_checkpoint': scrape_config.resume_from_checkpoint,
        'max_pages': scrape_config.max_pages,
        'start_page': scrape_config.start_page,
        'max_items': scrape_config.max_items,
        'finalize_missing': finalize_missing,
        'rerun_failed_pages': rerun_failed_pages,
        'rerun_url_count': len(rerun_urls),
    }

    async with AsyncSessionLocal() as session:
        service = LegacyCatalogSyncService(
            session,
            dry_run=dry_run,
            source_type='legacy_json_upload',
            source_name='mall_playwright_scrape',
            requested_by=requested_by,
            source_path=Path('mall_playwright_scrape'),
            job_type='catalog_mall_scrape_sync',
            batch_id=batch_id,
            finalize_missing=finalize_missing,
            missing_mark_threshold=missing_mark_threshold,
        )
        sync_result = await service.run_items(scrape_result.items)

    mall_batch['finished_at'] = datetime.now(timezone.utc).isoformat()
    sync_stats = sync_result.get('stats') or {}
    if isinstance(sync_stats, dict):
        sync_stats['mall_batch'] = mall_batch
        sync_stats['batch_id'] = batch_id
        sync_stats.setdefault('visibility', {})
        if isinstance(sync_stats.get('visibility'), dict):
            sync_stats['visibility']['finalize_missing'] = finalize_missing
            sync_stats['visibility']['missing_mark_threshold'] = missing_mark_threshold
    if not dry_run:
        job_id = ((sync_result.get('job') or {}).get('job_id') if isinstance(sync_result.get('job'), dict) else None)
        if job_id:
            await _attach_mall_scrape_stats_to_job(
                int(job_id),
                scrape_result=scrape_result,
                mall_batch=mall_batch,
            )

    return {
        **sync_result,
        'mall_batch': mall_batch,
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
                'crawl_mode': crawl_mode,
                'batch_id': batch_id,
                'finalize_missing': finalize_missing,
                'missing_mark_threshold': missing_mark_threshold,
                'rerun_failed_pages': rerun_failed_pages,
                'rerun_url_count': len(rerun_urls),
            },
        },
    }


async def _attach_mall_scrape_stats_to_job(
    job_id: int,
    *,
    scrape_result: MallScrapeResult,
    mall_batch: dict[str, Any],
) -> None:
    async with AsyncSessionLocal() as session:
        job = await session.get(SyncJob, job_id)
        if job is None:
            return
        stats_json = dict(job.stats_json or {})
        scrape_stats = scrape_result.stats.to_dict()
        stats_json['mall_batch'] = mall_batch
        stats_json['scrape'] = {
            'stats': scrape_stats,
            'visited_urls': scrape_result.visited_urls,
        }
        stats_json['page_records'] = scrape_stats.get('page_records') or []
        stats_json['failed_pages'] = scrape_stats.get('failed_pages') or []
        job.stats_json = stats_json
        session.add(
            SyncJobLog(
                job_id=job_id,
                level='warning' if scrape_stats.get('failed_pages') else 'info',
                event_type='mall_scrape_pages',
                message=(
                    f"商城抓取页级记录：页面 {scrape_stats.get('pages_visited', 0)}，"
                    f"提取 {scrape_stats.get('extracted_items', 0)}，"
                    f"失败页 {len(scrape_stats.get('failed_pages') or [])}。"
                ),
                context_json={
                    'mall_batch': mall_batch,
                    'page_records': scrape_stats.get('page_records') or [],
                    'failed_pages': scrape_stats.get('failed_pages') or [],
                    'checkpoint_path': scrape_stats.get('checkpoint_path'),
                    'checkpoint_status': scrape_stats.get('checkpoint_status'),
                },
            )
        )
        await session.commit()
