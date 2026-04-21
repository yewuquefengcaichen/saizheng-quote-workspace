from __future__ import annotations

import asyncio
import html
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from app.core.config import settings
from app.services.catalog_sync import normalize_text


BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DINGHUOVIP_PRODUCT_LIST_ADAPTER = 'dinghuovip_product_list'

PRODUCT_CODE_KEYS = (
    'code',
    'productCode',
    'product_code',
    'goodsCode',
    'goods_code',
    'skuCode',
    'sku_code',
    'itemCode',
    'item_code',
    'spuCode',
    'spu_code',
    'productNo',
    'goodsNo',
    'goodsSn',
    'sn',
    'barcode',
    'id',
    'productId',
    'goodsId',
)
PRODUCT_NAME_KEYS = (
    'name',
    'productName',
    'product_name',
    'goodsName',
    'goods_name',
    'title',
    'skuName',
    'itemName',
)
MODEL_KEYS = ('model', 'spec', 'specification', 'specText', 'skuSpec', 'goodsSpec', 'variantName')
CATEGORY_KEYS = ('category', 'categoryName', 'categoryPath', 'catName', 'className')
UNIT_KEYS = ('unit', 'unitName', 'measureUnit')
BRAND_KEYS = ('brand', 'brandName')
SUPPLIER_KEYS = ('supplier', 'supplierName', 'vendorName')
PRICE_KEYS = ('market_price', 'marketPrice', 'salePrice', 'price', 'mallPrice', 'retailPrice')
COST_PRICE_KEYS = ('cost_price', 'costPrice', 'purchasePrice', 'supplyPrice')
STATUS_KEYS = ('status', 'statusName', 'saleStatus', 'isOnSale', 'is_online', 'online')
INTRO_KEYS = ('intro', 'description', 'detail', 'content', 'goodsDesc', 'productDesc')
IMAGE_KEYS = (
    'image',
    'imageUrl',
    'image_url',
    'pic',
    'picUrl',
    'pic_url',
    'thumb',
    'thumbUrl',
    'mainImage',
    'mainPic',
    'cover',
    'url',
)


@dataclass
class MallScrapeConfig:
    start_url: str
    page_url_template: str | None = None
    max_pages: int = 3
    start_page: int = 1
    max_items: int = 0
    headless: bool = True
    storage_state_path: str | None = None
    page_timeout_ms: int = 30000
    page_delay_ms: int = 800
    next_delay_ms: int = 500
    detail_delay_ms: int = 500
    product_card_selector: str = settings.mall_scrape_product_card_selector
    next_selector: str = settings.mall_scrape_next_selector
    screenshot_path: str = 'output/playwright/mall-scrape-latest.png'
    checkpoint_path: str | None = None
    resume_from_checkpoint: bool = False
    field_map: dict[str, list[str]] = field(default_factory=dict)
    network_include_patterns: list[str] = field(default_factory=list)
    network_exclude_patterns: list[str] = field(default_factory=list)
    dom_table_selector: str | None = None
    site_adapter: str | None = None
    fetch_detail_images: bool = False
    detail_fetch_limit: int = 0
    detail_image_limit_per_item: int = 20


@dataclass
class MallScrapeStats:
    pages_visited: int = 0
    network_json_candidates: int = 0
    dom_candidates: int = 0
    detail_pages_visited: int = 0
    detail_images_found: int = 0
    extracted_items: int = 0
    deduped_items: int = 0
    current_url: str | None = None
    page_title: str | None = None
    login_suspected: bool = False
    screenshot_path: str | None = None
    warnings: list[str] = field(default_factory=list)
    checkpoint_path: str | None = None
    checkpoint_status: str | None = None
    resumed_from_checkpoint: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MallScrapeResult:
    items: list[dict[str, Any]]
    stats: MallScrapeStats
    visited_urls: list[str]
    raw_payload_examples: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            'items': self.items,
            'stats': self.stats.to_dict(),
            'visited_urls': self.visited_urls,
            'raw_payload_examples': self.raw_payload_examples,
        }


def build_default_mall_scrape_config(**overrides: Any) -> MallScrapeConfig:
    start_url = normalize_text(str(overrides.get('start_url') or settings.mall_scrape_start_url or settings.legacy_mall_base_url))
    page_url_template = normalize_text(str(overrides.get('page_url_template') or settings.mall_scrape_page_url_template or ''))
    storage_state_path = normalize_text(str(overrides.get('storage_state_path') or settings.mall_scrape_storage_state_path or ''))
    max_pages = _coerce_int(overrides.get('max_pages'), default=settings.mall_scrape_max_pages or 3, min_value=1, max_value=500)
    start_page = _coerce_int(overrides.get('start_page'), default=getattr(settings, 'mall_scrape_start_page', 1), min_value=1, max_value=500000)
    max_items = _coerce_int(overrides.get('max_items'), default=getattr(settings, 'mall_scrape_max_items', 0), min_value=0, max_value=200000)
    page_timeout_ms = _coerce_int(overrides.get('page_timeout_ms'), default=settings.mall_scrape_page_timeout_ms or 30000, min_value=5000, max_value=180000)
    page_delay_ms = _coerce_int(overrides.get('page_delay_ms'), default=getattr(settings, 'mall_scrape_page_delay_ms', 800), min_value=0, max_value=60000)
    next_delay_ms = _coerce_int(overrides.get('next_delay_ms'), default=getattr(settings, 'mall_scrape_next_delay_ms', getattr(settings, 'mall_scrape_next_page_delay_ms', 500)), min_value=0, max_value=60000)
    detail_delay_ms = _coerce_int(overrides.get('detail_delay_ms'), default=getattr(settings, 'mall_scrape_detail_delay_ms', getattr(settings, 'mall_scrape_detail_page_delay_ms', 500)), min_value=0, max_value=60000)
    checkpoint_path = normalize_text(str(overrides.get('checkpoint_path') or getattr(settings, 'mall_scrape_checkpoint_path', '') or ''))
    headless = overrides.get('headless')
    if headless is None:
        headless = settings.mall_scrape_headless

    if not start_url:
        start_url = settings.legacy_mall_base_url

    site_adapter = normalize_text(str(overrides.get('site_adapter') or getattr(settings, 'mall_scrape_site_adapter', '') or ''))
    dom_table_selector = normalize_text(str(overrides.get('dom_table_selector') or getattr(settings, 'mall_scrape_dom_table_selector', '') or ''))
    network_include_patterns = _normalize_pattern_list(
        overrides.get('network_include_patterns')
        if overrides.get('network_include_patterns') is not None
        else getattr(settings, 'mall_scrape_network_include_patterns', None)
    )
    network_exclude_patterns = _normalize_pattern_list(
        overrides.get('network_exclude_patterns')
        if overrides.get('network_exclude_patterns') is not None
        else getattr(settings, 'mall_scrape_network_exclude_patterns', None)
    )

    if site_adapter == DINGHUOVIP_PRODUCT_LIST_ADAPTER:
        dom_table_selector = dom_table_selector or '#productList'
        if not normalize_text(str(overrides.get('next_selector') or '')):
            overrides['next_selector'] = '.page_search_tool_area a.p:has-text("下一页"), a:has-text("下一页"), button:has-text("下一页")'
        if not network_include_patterns:
            network_include_patterns = ['/Product/']
        network_exclude_patterns = _dedupe_strings(
            network_exclude_patterns
            + [
                '/Notice/',
                '/ManuSysNotice',
                '/GetManuSysNotice',
            ]
        )

    return MallScrapeConfig(
        start_url=start_url,
        page_url_template=page_url_template or None,
        max_pages=max_pages,
        start_page=start_page,
        max_items=max_items,
        headless=bool(headless),
        storage_state_path=storage_state_path or None,
        page_timeout_ms=page_timeout_ms,
        page_delay_ms=page_delay_ms,
        next_delay_ms=next_delay_ms,
        detail_delay_ms=detail_delay_ms,
        product_card_selector=normalize_text(str(overrides.get('product_card_selector') or settings.mall_scrape_product_card_selector)) or settings.mall_scrape_product_card_selector,
        next_selector=normalize_text(str(overrides.get('next_selector') or settings.mall_scrape_next_selector)) or settings.mall_scrape_next_selector,
        screenshot_path=normalize_text(str(overrides.get('screenshot_path') or 'output/playwright/mall-scrape-latest.png')) or 'output/playwright/mall-scrape-latest.png',
        checkpoint_path=checkpoint_path or None,
        resume_from_checkpoint=_coerce_bool(
            overrides.get('resume_from_checkpoint')
            if overrides.get('resume_from_checkpoint') is not None
            else getattr(settings, 'mall_scrape_resume_from_checkpoint', False),
            default=False,
        ),
        field_map=overrides.get('field_map') if isinstance(overrides.get('field_map'), dict) else {},
        network_include_patterns=network_include_patterns,
        network_exclude_patterns=network_exclude_patterns,
        dom_table_selector=dom_table_selector or None,
        site_adapter=site_adapter or None,
        fetch_detail_images=_coerce_bool(
            overrides.get('fetch_detail_images')
            if overrides.get('fetch_detail_images') is not None
            else getattr(settings, 'mall_scrape_fetch_detail_images', False),
            default=False,
        ),
        detail_fetch_limit=_coerce_int(overrides.get('detail_fetch_limit'), default=getattr(settings, 'mall_scrape_detail_fetch_limit', 0), min_value=0, max_value=10000),
        detail_image_limit_per_item=_coerce_int(overrides.get('detail_image_limit_per_item'), default=getattr(settings, 'mall_scrape_detail_image_limit_per_item', 20), min_value=1, max_value=80),
    )


def _coerce_int(value: Any, *, default: int, min_value: int, max_value: int) -> int:
    try:
        if value in (None, ''):
            number = int(default)
        else:
            number = int(value)
    except Exception:
        number = int(default)
    return max(min_value, min(max_value, number))


def _coerce_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ('1', 'true', 'yes', 'y', 'on', '是'):
        return True
    if text in ('0', 'false', 'no', 'n', 'off', '否'):
        return False
    return default


def _normalize_pattern_list(value: Any) -> list[str]:
    if value in (None, ''):
        return []
    raw_items: list[Any]
    if isinstance(value, str):
        raw_items = re.split(r'[\n,;]+', value)
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        raw_items = [value]
    return _dedupe_strings([normalize_text(str(item or '')) or '' for item in raw_items])


def _dedupe_strings(items: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = normalize_text(str(item or ''))
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped


def _resolve_runtime_path(value: str | None) -> Path | None:
    text = normalize_text(str(value or ''))
    if not text:
        return None
    path = Path(text)
    if path.is_absolute():
        return path
    first_part = path.parts[0].lower() if path.parts else ''
    if first_part == 'storage':
        return BACKEND_ROOT / path
    return PROJECT_ROOT / path


def _pattern_matches(value: str, pattern: str) -> bool:
    if not pattern:
        return False
    if pattern.startswith('re:'):
        try:
            return re.search(pattern[3:], value, re.IGNORECASE) is not None
        except re.error:
            return False
    return pattern.lower() in value.lower()


def _is_url_allowed_by_patterns(url: str, *, include_patterns: list[str], exclude_patterns: list[str]) -> bool:
    url = str(url or '')
    if not url:
        return False
    if any(_pattern_matches(url, pattern) for pattern in exclude_patterns):
        return False
    if include_patterns and not any(_pattern_matches(url, pattern) for pattern in include_patterns):
        return False
    return True


def _pick_value(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in payload and payload[key] not in (None, ''):
            return payload[key]
    lower_map = {str(key).lower(): value for key, value in payload.items()}
    for key in keys:
        value = lower_map.get(key.lower())
        if value not in (None, ''):
            return value
    return None


def _field_keys(field_map: dict[str, list[str]] | None, field_name: str, defaults: tuple[str, ...]) -> tuple[str, ...]:
    custom = []
    if isinstance(field_map, dict):
        raw_keys = field_map.get(field_name) or []
        if isinstance(raw_keys, str):
            raw_keys = [raw_keys]
        custom = [str(key) for key in raw_keys if normalize_text(str(key))]
    return tuple(custom) + defaults


def _stringify_value(value: Any) -> str | None:
    if value in (None, ''):
        return None
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return normalize_text(value)
    return normalize_text(str(value))


def _extract_price(value: Any) -> str | None:
    text = _stringify_value(value)
    if not text:
        return None
    match = re.search(r'-?\d+(?:\.\d+)?', text.replace(',', ''))
    return match.group(0) if match else None


def _collect_image_urls(value: Any, *, base_url: str, limit: int = 20) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()

    def add(raw: Any) -> None:
        text = _stringify_value(raw)
        if not text:
            return
        if not re.search(r'\.(?:jpg|jpeg|png|gif|webp|bmp)(?:\?|$)', text, re.IGNORECASE) and not text.startswith(('http://', 'https://', '//', '/')):
            return
        if text.startswith('//'):
            text = f'https:{text}'
        text = urljoin(base_url, text)
        if text not in seen and len(urls) < limit:
            seen.add(text)
            urls.append(text)

    def walk(node: Any) -> None:
        if len(urls) >= limit:
            return
        if isinstance(node, dict):
            for key, item in node.items():
                if str(key) in IMAGE_KEYS or 'image' in str(key).lower() or 'pic' in str(key).lower():
                    if isinstance(item, list):
                        for child in item:
                            walk(child)
                    elif isinstance(item, dict):
                        walk(item)
                    else:
                        add(item)
                elif isinstance(item, (dict, list)):
                    walk(item)
        elif isinstance(node, list):
            for child in node:
                walk(child)
        else:
            add(node)

    walk(value)
    return urls


def _looks_like_product(payload: dict[str, Any]) -> bool:
    name = _pick_value(payload, PRODUCT_NAME_KEYS)
    code = _pick_value(payload, PRODUCT_CODE_KEYS)
    price = _pick_value(payload, PRICE_KEYS)
    return bool(name and (code or price or _pick_value(payload, IMAGE_KEYS)))


def _walk_product_payloads(payload: Any, *, limit: int = 1000) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if len(found) >= limit:
            return
        if isinstance(node, dict):
            if _looks_like_product(node):
                found.append(node)
            for value in node.values():
                if isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return found


def _map_status(value: Any) -> str:
    if isinstance(value, bool):
        return '上架' if value else '下架'
    text = _stringify_value(value)
    if not text:
        return '上架'
    if text in ('1', 'true', 'True', '上架', '销售中', '启用', 'active', 'online'):
        return '上架'
    if text in ('0', 'false', 'False', '下架', '停售', '禁用', 'inactive', 'offline'):
        return '下架'
    return text


def compact_payload_example(payload: dict[str, Any], *, max_text: int = 2000) -> dict[str, Any]:
    text = str(payload)
    if len(text) > max_text:
        text = text[:max_text] + '...'
    return {
        'keys': list(payload.keys())[:50],
        'preview': text,
    }


def map_payload_to_legacy_item(payload: dict[str, Any], *, base_url: str, field_map: dict[str, list[str]] | None = None) -> dict[str, Any] | None:
    name = _stringify_value(_pick_value(payload, _field_keys(field_map, 'name', PRODUCT_NAME_KEYS)))
    code = _stringify_value(_pick_value(payload, _field_keys(field_map, 'code', PRODUCT_CODE_KEYS)))
    if not name:
        return None
    if not code:
        raw_id = _stringify_value(_pick_value(payload, ('id', 'productId', 'goodsId')))
        code = f'mall-{raw_id}' if raw_id else None
    if not code:
        return None

    images = _collect_image_urls(payload, base_url=base_url)
    intro_parts = []
    intro_text = _stringify_value(_pick_value(payload, INTRO_KEYS))
    if intro_text:
        intro_parts.append(html.escape(intro_text))
    intro_parts.extend(f'<img src="{html.escape(url)}">' for url in images)

    item = {
        'code': code,
        'name': name,
        'model': _stringify_value(_pick_value(payload, _field_keys(field_map, 'model', MODEL_KEYS))) or '',
        'category': _stringify_value(_pick_value(payload, _field_keys(field_map, 'category', CATEGORY_KEYS))) or '',
        'unit': _stringify_value(_pick_value(payload, _field_keys(field_map, 'unit', UNIT_KEYS))) or '',
        'market_price': _extract_price(_pick_value(payload, _field_keys(field_map, 'market_price', PRICE_KEYS))) or '',
        'cost_price': _extract_price(_pick_value(payload, _field_keys(field_map, 'cost_price', COST_PRICE_KEYS))) or '',
        'brand': _stringify_value(_pick_value(payload, _field_keys(field_map, 'brand', BRAND_KEYS))) or '',
        'supplier': _stringify_value(_pick_value(payload, _field_keys(field_map, 'supplier', SUPPLIER_KEYS))) or '',
        'status': _map_status(_pick_value(payload, _field_keys(field_map, 'status', STATUS_KEYS))),
        'intro': ''.join(intro_parts),
        'mall_source_payload': payload,
    }
    if images:
        item['image_urls'] = images
        item['primary_image_url'] = images[0]
    detail_images = payload.get('detail_image_urls')
    if isinstance(detail_images, list) and detail_images:
        item['detail_image_urls'] = detail_images
        item['detail_image_count'] = len(detail_images)
    detail_url = _stringify_value(payload.get('detail_url') or payload.get('detailUrl') or payload.get('href'))
    if detail_url:
        item['detail_url'] = urljoin(base_url, detail_url)
    image_sync_mode = _stringify_value(payload.get('image_sync_mode') or payload.get('imageSyncMode'))
    if image_sync_mode:
        item['image_sync_mode'] = image_sync_mode
    return item


class MallPlaywrightScraper:
    def __init__(self, config: MallScrapeConfig) -> None:
        self.config = config
        self.stats = MallScrapeStats()
        self.stats.checkpoint_path = config.checkpoint_path
        self.visited_urls: list[str] = []
        self._raw_payloads: list[dict[str, Any]] = []

    async def scrape(self) -> MallScrapeResult:
        try:
            from playwright.async_api import async_playwright
        except Exception as exc:  # pragma: no cover - depends on local optional dependency
            raise RuntimeError('Playwright 未安装，请先执行 pip install playwright && playwright install chromium') from exc

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=self.config.headless)
            context_options: dict[str, Any] = {}
            if self.config.storage_state_path:
                state_path = _resolve_runtime_path(self.config.storage_state_path)
                if state_path.exists():
                    context_options['storage_state'] = str(state_path)
                else:
                    self.stats.warnings.append(f'登录态文件不存在: {state_path}')

            context = await browser.new_context(**context_options)
            page = await context.new_page()
            page.set_default_timeout(self.config.page_timeout_ms)

            response_tasks: set[asyncio.Task[Any]] = set()

            async def capture_response(response: Any) -> None:
                content_type = (response.headers or {}).get('content-type', '')
                if 'json' not in content_type.lower():
                    return
                if not self._should_capture_response(response.url):
                    return
                try:
                    payload = await response.json()
                except Exception:
                    return
                nodes = _walk_product_payloads(payload)
                if nodes:
                    self.stats.network_json_candidates += len(nodes)
                    self._raw_payloads.extend(nodes)

            def on_response(response: Any) -> None:
                task = asyncio.create_task(capture_response(response))
                response_tasks.add(task)
                task.add_done_callback(response_tasks.discard)

            page.on('response', on_response)

            try:
                await self._visit_pages(page)
                await self._capture_page_state(page)
                if response_tasks:
                    await asyncio.gather(*response_tasks, return_exceptions=True)
                if not self._raw_payloads:
                    await self._save_debug_screenshot(page)
            finally:
                await context.close()
                await browser.close()

        items = self._dedupe_items(
            item
            for payload in self._raw_payloads
            if (item := map_payload_to_legacy_item(payload, base_url=self.config.start_url, field_map=self.config.field_map))
        )
        if self.config.max_items and len(items) > self.config.max_items:
            items = items[: self.config.max_items]
            self.stats.deduped_items = len(items)
        self.stats.extracted_items = len(items)
        if not items and self.stats.login_suspected:
            self.stats.warnings.append('疑似进入登录页或登录态失效，请先配置 storage_state_path。')
        return MallScrapeResult(
            items=items,
            stats=self.stats,
            visited_urls=self.visited_urls,
            raw_payload_examples=[compact_payload_example(payload) for payload in self._raw_payloads[:5]],
        )

    async def _capture_page_state(self, page: Any) -> None:
        try:
            self.stats.current_url = page.url
            self.stats.page_title = await page.title()
            body_text = await page.locator('body').inner_text(timeout=3000)
            login_words = ('登录', '用户名', '密码', '验证码', '请登录', 'login', 'password')
            lowered_url = str(page.url or '').lower()
            lowered_title = str(self.stats.page_title or '').lower()
            lowered_body = body_text.lower()
            self.stats.login_suspected = (
                'login' in lowered_url
                or 'login' in lowered_title
                or any(word.lower() in lowered_body for word in login_words)
            )
        except Exception as exc:
            self.stats.warnings.append(f'页面状态检测失败: {str(exc)[:200]}')

    async def _save_debug_screenshot(self, page: Any) -> None:
        try:
            screenshot_path = _resolve_runtime_path(self.config.screenshot_path) or Path(self.config.screenshot_path)
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(screenshot_path), full_page=True)
            self.stats.screenshot_path = str(screenshot_path)
        except Exception as exc:
            self.stats.warnings.append(f'调试截图保存失败: {str(exc)[:200]}')

    async def _visit_pages(self, page: Any) -> None:
        start_page, current_url = self._resolve_resume_cursor()
        end_page = start_page + self.config.max_pages - 1
        last_page_index = start_page - 1
        last_page_url = current_url

        for page_index in range(start_page, end_page + 1):
            target_url = self._page_url(page_index, current_url)
            await page.goto(target_url, wait_until='domcontentloaded', timeout=self.config.page_timeout_ms)
            self.visited_urls.append(page.url)
            self.stats.pages_visited += 1
            last_page_index = page_index
            last_page_url = page.url
            try:
                await page.wait_for_load_state('networkidle', timeout=min(self.config.page_timeout_ms, 15000))
            except Exception:
                pass
            await page.wait_for_timeout(self.config.page_delay_ms)
            dom_payloads = await self._extract_dom_payloads(page)
            if self.config.fetch_detail_images and dom_payloads:
                dom_payloads = await self._enrich_payloads_with_detail_images(page, dom_payloads)
            self._raw_payloads.extend(dom_payloads)
            self._write_checkpoint(
                status='processed_page',
                page_index=page_index,
                page_url=page.url,
                raw_payload_count=len(self._raw_payloads),
                dom_payload_count=len(dom_payloads),
            )

            if self.config.max_items and len(self._raw_payloads) >= self.config.max_items:
                self.stats.checkpoint_status = 'max_items_reached'
                checkpoint_extra: dict[str, Any] = {}
                if self.config.page_url_template:
                    checkpoint_extra['next_page_index'] = page_index + 1
                else:
                    next_url = await self._find_next_page_href(page)
                    if next_url:
                        checkpoint_extra['next_page_index'] = page_index + 1
                        checkpoint_extra['next_url'] = next_url
                self._write_checkpoint(
                    status='max_items_reached',
                    page_index=page_index,
                    page_url=page.url,
                    raw_payload_count=len(self._raw_payloads),
                    **checkpoint_extra,
                )
                break

            if self.config.page_url_template:
                continue
            if page_index >= end_page:
                break
            clicked = await self._click_next(page)
            if not clicked:
                self.stats.checkpoint_status = 'no_next_page'
                self._write_checkpoint(
                    status='no_next_page',
                    page_index=page_index,
                    page_url=page.url,
                    raw_payload_count=len(self._raw_payloads),
                )
                break
            current_url = page.url
            self._write_checkpoint(
                status='next_ready',
                page_index=page_index,
                page_url=target_url,
                next_page_index=page_index + 1,
                next_url=current_url,
                raw_payload_count=len(self._raw_payloads),
            )

        if self.stats.checkpoint_status not in {'max_items_reached', 'no_next_page'}:
            self.stats.checkpoint_status = 'page_limit_reached'
            checkpoint_extra: dict[str, Any] = {}
            if self.config.page_url_template:
                checkpoint_extra['next_page_index'] = last_page_index + 1
            else:
                next_url = await self._find_next_page_href(page)
                if next_url:
                    checkpoint_extra['next_page_index'] = last_page_index + 1
                    checkpoint_extra['next_url'] = next_url
            self._write_checkpoint(
                status='page_limit_reached',
                page_index=last_page_index,
                page_url=self.visited_urls[-1] if self.visited_urls else last_page_url,
                raw_payload_count=len(self._raw_payloads),
                **checkpoint_extra,
            )

    def _resolve_resume_cursor(self) -> tuple[int, str]:
        start_page = max(1, int(self.config.start_page or 1))
        current_url = self.config.start_url
        if not self.config.resume_from_checkpoint or not self.config.checkpoint_path:
            return start_page, current_url

        checkpoint_path = _resolve_runtime_path(self.config.checkpoint_path) or Path(self.config.checkpoint_path)
        if not checkpoint_path.exists():
            return start_page, current_url

        try:
            checkpoint = json.loads(checkpoint_path.read_text(encoding='utf-8'))
        except Exception as exc:
            self.stats.warnings.append(f'断点文件读取失败，将从配置起点开始: {str(exc)[:200]}')
            return start_page, current_url

        try:
            next_page_index = int(checkpoint.get('next_page_index') or 0)
        except Exception:
            next_page_index = 0
        try:
            last_page_index = int(checkpoint.get('last_page_index') or 0)
        except Exception:
            last_page_index = 0

        next_url = normalize_text(str(checkpoint.get('next_url') or ''))
        last_url = normalize_text(str(checkpoint.get('last_url') or checkpoint.get('page_url') or ''))
        status = normalize_text(str(checkpoint.get('status') or '')) or ''

        if next_page_index > 0:
            start_page = max(start_page, next_page_index)
        elif self.config.page_url_template and last_page_index > 0:
            start_page = max(start_page, last_page_index + 1)

        if not self.config.page_url_template:
            if next_url:
                current_url = next_url
            elif status in {'done', 'no_next_page'}:
                self.stats.warnings.append('断点显示已到末页，如需重跑请关闭 resume_from_checkpoint 或删除断点文件。')
            elif last_url:
                self.stats.warnings.append('断点文件没有下一页 URL，非模板分页只能从最后记录 URL 尝试继续。')
                current_url = last_url

        self.stats.resumed_from_checkpoint = True
        self.stats.checkpoint_status = f'resumed:{status or "unknown"}'
        return start_page, current_url

    def _write_checkpoint(self, *, status: str, page_index: int, page_url: str, **extra: Any) -> None:
        if not self.config.checkpoint_path:
            self.stats.checkpoint_status = status
            return

        checkpoint_path = _resolve_runtime_path(self.config.checkpoint_path) or Path(self.config.checkpoint_path)
        try:
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                'status': status,
                'updated_at': datetime.now(timezone.utc).isoformat(),
                'last_page_index': page_index,
                'last_url': page_url,
                'pages_visited': self.stats.pages_visited,
                'network_json_candidates': self.stats.network_json_candidates,
                'dom_candidates': self.stats.dom_candidates,
                'raw_payload_count': len(self._raw_payloads),
                'config': {
                    'start_url': self.config.start_url,
                    'page_url_template': self.config.page_url_template,
                    'max_pages': self.config.max_pages,
                    'start_page': self.config.start_page,
                    'max_items': self.config.max_items,
                    'site_adapter': self.config.site_adapter,
                    'fetch_detail_images': self.config.fetch_detail_images,
                },
                **extra,
            }
            tmp_path = checkpoint_path.with_suffix(checkpoint_path.suffix + '.tmp')
            tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
            tmp_path.replace(checkpoint_path)
            self.stats.checkpoint_path = str(checkpoint_path)
            self.stats.checkpoint_status = status
        except Exception as exc:
            self.stats.warnings.append(f'断点文件写入失败: {str(exc)[:200]}')

    def _page_url(self, page_index: int, fallback_url: str) -> str:
        if self.config.page_url_template:
            return self.config.page_url_template.format(page=page_index)
        return fallback_url

    async def _click_next(self, page: Any) -> bool:
        try:
            next_href = await self._find_next_page_href(page)
            if next_href:
                await page.goto(next_href, wait_until='domcontentloaded', timeout=self.config.page_timeout_ms)
                try:
                    await page.wait_for_load_state('networkidle', timeout=min(self.config.page_timeout_ms, 15000))
                except Exception:
                    pass
                await page.wait_for_timeout(self.config.next_delay_ms)
                return True

            next_locator = page.locator(self.config.next_selector).first
            if await next_locator.count() < 1:
                return False
            if not await next_locator.is_enabled():
                return False
            old_url = page.url
            await next_locator.click()
            try:
                await page.wait_for_url(lambda url: str(url) != old_url, timeout=min(self.config.page_timeout_ms, 10000))
            except Exception:
                pass
            try:
                await page.wait_for_load_state('networkidle', timeout=min(self.config.page_timeout_ms, 15000))
            except Exception:
                pass
            await page.wait_for_timeout(self.config.next_delay_ms)
            return True
        except Exception as exc:
            self.stats.warnings.append(f'下一页点击失败: {str(exc)[:200]}')
            return False

    async def _find_next_page_href(self, page: Any) -> str | None:
        try:
            href = await page.evaluate(
                """() => {
                    const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                    const links = Array.from(document.querySelectorAll('a[href]'));
                    const candidate = links.find((link) => {
                        const text = clean(link.innerText || link.textContent || '');
                        const cls = String(link.className || '');
                        if (!text.includes('下一页')) return false;
                        if (/disable|disabled/i.test(cls)) return false;
                        return !!link.href;
                    });
                    return candidate ? candidate.href : '';
                }"""
            )
            return _stringify_value(href)
        except Exception:
            return None

    async def _extract_dom_payloads(self, page: Any) -> list[dict[str, Any]]:
        if self.config.site_adapter == DINGHUOVIP_PRODUCT_LIST_ADAPTER:
            return await self._extract_dinghuovip_product_list_payloads(page)

        try:
            payloads = await page.locator(self.config.product_card_selector).evaluate_all(
                """nodes => nodes.slice(0, 1000).map((node) => {
                    const text = (node.innerText || node.textContent || '').trim();
                    const img = node.querySelector('img');
                    const link = node.querySelector('a[href]');
                    const dataset = Object.assign({}, node.dataset || {});
                    const firstLine = text.split('\\n').map(v => v.trim()).filter(Boolean)[0] || '';
                    return {
                        id: dataset.productId || dataset.goodsId || dataset.id || '',
                        code: dataset.code || dataset.productCode || dataset.goodsCode || dataset.skuCode || '',
                        name: dataset.name || dataset.productName || dataset.goodsName || firstLine,
                        title: dataset.title || node.getAttribute('title') || '',
                        price: dataset.price || (text.match(/[¥￥]?\\s*\\d+(?:\\.\\d+)?/) || [''])[0],
                        imageUrl: img ? (img.currentSrc || img.src || img.getAttribute('data-src') || img.getAttribute('src') || '') : '',
                        href: link ? link.href : '',
                        description: text.slice(0, 1000)
                    };
                })"""
            )
            self.stats.dom_candidates += len(payloads)
            return payloads
        except Exception as exc:
            self.stats.warnings.append(f'DOM 商品卡片提取失败: {str(exc)[:200]}')
            return []

    def _should_capture_response(self, url: str) -> bool:
        return _is_url_allowed_by_patterns(
            url,
            include_patterns=self.config.network_include_patterns,
            exclude_patterns=self.config.network_exclude_patterns,
        )

    async def _extract_dinghuovip_product_list_payloads(self, page: Any) -> list[dict[str, Any]]:
        selector = self.config.dom_table_selector or '#productList'
        try:
            payloads = await page.evaluate(
                """(selector) => {
                    const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                    const price = (value) => {
                        const match = clean(value).replace(/,/g, '').match(/-?\\d+(?:\\.\\d+)?/);
                        return match ? match[0] : '';
                    };
                    const firstImageUrl = (row) => {
                        const img = row.querySelector('img');
                        if (!img) return '';
                        return img.currentSrc
                            || img.getAttribute('data-original')
                            || img.getAttribute('data-src')
                            || img.getAttribute('src')
                            || '';
                    };
                    const pickDetailUrl = (row) => {
                        const links = Array.from(row.querySelectorAll('a[href]'));
                        const detail = links.find((link) => String(link.getAttribute('href') || '').includes('/Product/ProductInfo'));
                        return detail ? detail.href : (links[0] ? links[0].href : '');
                    };
                    let rows = Array.from(document.querySelectorAll(`${selector} tr`));
                    if (!rows.length) {
                        rows = Array.from(document.querySelectorAll(selector));
                    }
                    return rows.slice(0, 1000).map((row) => {
                        const cells = Array.from(row.cells || []);
                        const nameCell = cells[1] || row;
                        const nameText = clean(nameCell.innerText || nameCell.textContent || '');
                        const lines = String(nameCell.innerText || nameCell.textContent || '')
                            .split('\\n')
                            .map(clean)
                            .filter(Boolean);
                        const codeMatch = nameText.match(/编码[:：]\\s*([A-Za-z0-9_-]+)/);
                        const code = codeMatch ? codeMatch[1] : '';
                        const nameLine = lines.find((line) => {
                            if (!line || /编码[:：]/.test(line)) return false;
                            if (/^(详情|修改|删除|上架|下架)$/.test(line)) return false;
                            if (/^￥?\\d+(?:\\.\\d+)?$/.test(line)) return false;
                            return true;
                        }) || '';
                        const imageUrl = firstImageUrl(row);
                        const detailUrl = pickDetailUrl(row);
                        return {
                            source: 'dinghuovip_product_list_dom',
                            code,
                            productCode: code,
                            name: nameLine,
                            productName: nameLine,
                            model: clean(cells[2]?.innerText || ''),
                            market_price: price(cells[3]?.innerText || ''),
                            cost_price: price(cells[4]?.innerText || ''),
                            supplier: clean(cells[8]?.innerText || ''),
                            status: clean(cells[10]?.innerText || ''),
                            created_at: clean(cells[12]?.innerText || ''),
                            primary_image_url: imageUrl,
                            image_urls: imageUrl ? [imageUrl] : [],
                            detail_url: detailUrl,
                            image_sync_mode: 'append_only',
                            intro: nameText,
                            raw_text: clean(row.innerText || row.textContent || '')
                        };
                    }).filter((item) => item.code && item.name);
                }""",
                selector,
            )
            self.stats.dom_candidates += len(payloads)
            return payloads
        except Exception as exc:
            self.stats.warnings.append(f'dinghuovip 商品表格提取失败: {str(exc)[:200]}')
            return []

    async def _enrich_payloads_with_detail_images(self, page: Any, payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        limit = self.config.detail_fetch_limit or len(payloads)
        enriched: list[dict[str, Any]] = []
        detail_page = await page.context.new_page()
        detail_page.set_default_timeout(self.config.page_timeout_ms)
        try:
            for payload in payloads:
                item = dict(payload)
                detail_url = _stringify_value(item.get('detail_url') or item.get('href'))
                if detail_url and self.stats.detail_pages_visited < limit:
                    try:
                        detail_images = await self._extract_detail_image_urls(detail_page, detail_url)
                        if detail_images:
                            existing_images = list(item.get('image_urls') or [])
                            item['detail_image_urls'] = detail_images
                            item['image_urls'] = _dedupe_strings(existing_images + detail_images)
                            if item.get('image_urls'):
                                item['primary_image_url'] = item['image_urls'][0]
                            item['image_sync_mode'] = 'replace'
                            self.stats.detail_images_found += len(detail_images)
                    except Exception as exc:
                        self.stats.warnings.append(f'详情图提取失败: {str(exc)[:200]}')
                enriched.append(item)
        finally:
            await detail_page.close()
        return enriched

    async def _extract_detail_image_urls(self, detail_page: Any, detail_url: str) -> list[str]:
        await detail_page.goto(detail_url, wait_until='domcontentloaded', timeout=self.config.page_timeout_ms)
        self.stats.detail_pages_visited += 1
        try:
            await detail_page.wait_for_load_state('networkidle', timeout=min(self.config.page_timeout_ms, 15000))
        except Exception:
            pass
        await detail_page.wait_for_timeout(self.config.detail_delay_ms)
        urls = await detail_page.evaluate(
            """(limit) => {
                const urls = [];
                const seen = new Set();
                const add = (raw, width, height) => {
                    const url = String(raw || '').trim();
                    if (!url || seen.has(url)) return;
                    if (!/ProductImg|ProductDescription/i.test(url)) return;
                    if (/\\/S[A-Za-z0-9_-]+\\.(?:jpg|jpeg|png|webp)(?:\\?|$)/i.test(url)) return;
                    if (width && height && width < 100 && height < 100) return;
                    seen.add(url);
                    urls.push(url);
                };
                for (const img of Array.from(document.images)) {
                    add(
                        img.currentSrc
                            || img.getAttribute('data-original')
                            || img.getAttribute('data-src')
                            || img.getAttribute('src')
                            || '',
                        img.naturalWidth,
                        img.naturalHeight
                    );
                    if (urls.length >= limit) break;
                }
                return urls.slice(0, limit);
            }""",
            self.config.detail_image_limit_per_item,
        )
        return _dedupe_strings([urljoin(detail_url, str(url)) for url in (urls or [])])

    def _dedupe_items(self, items: Any) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in items:
            code = normalize_text(str(item.get('code') or ''))
            name = normalize_text(str(item.get('name') or ''))
            key = code or name
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        self.stats.deduped_items = len(deduped)
        if not deduped:
            self.stats.warnings.append('未提取到商品；请检查商城登录态、起始 URL 或商品卡片选择器。')
        return deduped
