# -*- coding: utf-8 -*-
"""
一键报价系统 - Flask后端
功能：上传报价单、匹配商城商品、人工确认、导出报价单
"""

from flask import Flask, render_template, request, jsonify, send_file, send_from_directory, Response, stream_with_context, redirect
from werkzeug.utils import secure_filename
import asyncio
import os
import json
import math
import html
import hashlib
import re
import sys
import threading
import pandas as pd
from datetime import datetime
from pathlib import Path

# 导入自定义模块
from utils.excel_handler import ExcelHandler
from utils.matcher import ProductMatcher, get_match_feedback_payload, build_mapping_signature
from utils.smart_parser import SmartQuoteParser
from utils.database import QuoteHistoryDB
from utils.image_handler import ProductImageHandler, get_image_url_from_product
from utils.normalizer import normalize_quote_item

BACKEND_ROOT = Path(__file__).resolve().parent / 'backend'
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

try:
    from sqlalchemy import func as sa_func, or_, select as sa_select
    from sqlalchemy.orm import selectinload
    from app.db.session import AsyncSessionLocal as V2AsyncSessionLocal
    from app.models import (
        Brand as V2Brand,
        Category as V2Category,
        ImageAsset as V2ImageAsset,
        Product as V2Product,
        ProductImage as V2ProductImage,
        ProductVariant as V2ProductVariant,
        Supplier as V2Supplier,
    )
    from app.services.catalog_sync import (
        LegacyCatalogSyncService as V2LegacyCatalogSyncService,
        build_sync_job_summary as v2_build_sync_job_summary,
        get_latest_catalog_sync_job as v2_get_latest_catalog_sync_job,
    )
    from app.services.image_embedding import (
        CLIP_PLACEHOLDER_MODEL_NAME as V2_CLIP_EMBEDDING_MODEL_NAME,
        CLIP_PLACEHOLDER_PROVIDER as V2_CLIP_EMBEDDING_PROVIDER,
        DEFAULT_EMBEDDING_MODEL_NAME as V2_IMAGE_EMBEDDING_MODEL_NAME,
        DEFAULT_EMBEDDING_PROVIDER as V2_IMAGE_EMBEDDING_PROVIDER,
        DEFAULT_EMBEDDING_VECTOR_DIM as V2_IMAGE_EMBEDDING_VECTOR_DIM,
        compute_query_image_features_for_provider as v2_compute_query_image_features_for_provider,
        get_image_embedding_status as v2_get_image_embedding_status,
        resolve_archive_file_path as v2_resolve_archive_file_path,
        search_similar_products as v2_search_similar_products,
    )
    from app.services.mall_sync import (
        pick_mall_scrape_options as v2_pick_mall_scrape_options,
        run_mall_scrape_sync_async as v2_run_mall_scrape_sync_async,
    )
    from app.core.celery_app import celery_app as V2CeleryApp
    from app.tasks.embedding import generate_image_embeddings_task as V2GenerateImageEmbeddingsTask
    from app.tasks.catalog import scrape_mall_sync_task as V2ScrapeMallSyncTask
    V2_IMAGE_SEARCH_AVAILABLE = True
    V2_IMAGE_SEARCH_IMPORT_ERROR = ''
    V2_CATALOG_AVAILABLE = True
    V2_CATALOG_IMPORT_ERROR = ''
except Exception as e:
    print(f"V2图搜图模块导入失败，将跳过图片检索能力: {e}")
    V2_IMAGE_SEARCH_AVAILABLE = False
    V2_IMAGE_SEARCH_IMPORT_ERROR = str(e)
    V2_CATALOG_AVAILABLE = False
    V2_CATALOG_IMPORT_ERROR = str(e)

# AI服务模块（可选，如果依赖未安装则降级）
try:
    from utils.ai_service import get_ai_service, AIService
    from utils.ai_matcher import AIProductMatcher, create_matcher
    AI_AVAILABLE = True
except ImportError as e:
    print(f"AI模块导入失败，将使用传统匹配: {e}")
    AI_AVAILABLE = False

app = Flask(__name__)
APP_BUILD = 'ocr-fix-v3'
app.config['UPLOAD_FOLDER'] = 'data'
app.config['OUTPUT_FOLDER'] = 'output'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 最大50MB

# 允许的文件扩展名
ALLOWED_EXTENSIONS = {'xls', 'xlsx', 'csv'}

# 全局变量存储数据
products_data = None
products_data_source = 'none'
matcher = None
quote_items = []
match_results = []
smart_parser = None
parse_result_cache = None  # 缓存解析结果，等待用户确认
quote_db = None  # 报价历史数据库
ai_service = None  # AI服务实例
use_ai_matcher = True  # 是否使用AI匹配器
_async_runtime_loop = None
_async_runtime_thread = None
_async_runtime_lock = threading.Lock()
current_match_context = {
    'source_type': '',
    'template_name': '',
    'template_hit': False,
    'mapping_changed': False,
    'mapping_signature': ''
}


def _ensure_async_runtime_loop():
    global _async_runtime_loop, _async_runtime_thread

    with _async_runtime_lock:
        if _async_runtime_loop and _async_runtime_loop.is_running():
            return _async_runtime_loop

        loop = asyncio.new_event_loop()

        def _loop_worker():
            asyncio.set_event_loop(loop)
            loop.run_forever()

        thread = threading.Thread(
            target=_loop_worker,
            name='quote-v2-async-runtime',
            daemon=True
        )
        thread.start()

        _async_runtime_loop = loop
        _async_runtime_thread = thread
        return _async_runtime_loop


def _run_async_task(coro):
    loop = _ensure_async_runtime_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()


def allowed_file(filename):
    """检查文件扩展名是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _is_truthy_form_value(value) -> bool:
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _set_runtime_products_snapshot(products, source='legacy_json'):
    global products_data, products_data_source, matcher

    products_data = list(products or [])
    products_data_source = source if products_data else 'none'
    matcher = ProductMatcher(products_data) if products_data else None
    return bool(products_data)


def _prepare_v2_products_for_runtime(products):
    prepared = []
    for product in products or []:
        item = _annotate_product_cost_fields(dict(product or {}), source='loaded')
        item['source'] = item.get('source') or 'postgres_v2'
        item['catalog_source'] = 'postgres_v2'
        images = [dict(image or {}) for image in (item.get('images') or [])]
        item['images'] = images
        if not item.get('image_url') and images:
            item['image_url'] = _normalize_text_value(images[0].get('url'))
        if not item.get('source_image_url') and images:
            item['source_image_url'] = _normalize_text_value(images[0].get('source_url') or images[0].get('url'))
        item['image_count'] = len(images)
        item['has_image'] = bool(item.get('image_url') or item.get('source_image_url') or images)
        prepared.append(item)
    return prepared


async def _load_v2_products_for_runtime_async():
    if not V2_CATALOG_AVAILABLE:
        return []

    async with V2AsyncSessionLocal() as session:
        products = list((
            await session.scalars(
                sa_select(V2Product)
                .options(
                    selectinload(V2Product.brand),
                    selectinload(V2Product.category),
                    selectinload(V2Product.supplier),
                    selectinload(V2Product.variants),
                    selectinload(V2Product.images),
                )
                .order_by(V2Product.id.asc())
            )
        ).all())

    return _prepare_v2_products_for_runtime([
        _normalize_v2_catalog_product_item(product, index=index)
        for index, product in enumerate(products)
    ])


def load_products():
    """加载商品库"""
    global products_data, products_data_source, matcher

    if V2_CATALOG_AVAILABLE:
        try:
            v2_products = _run_async_task(_load_v2_products_for_runtime_async())
            if v2_products:
                return _set_runtime_products_snapshot(v2_products, source='postgres_v2')
        except Exception as exc:
            print(f'从 PostgreSQL V2 加载商品库失败，回退到 JSON：{exc}')

    products_file = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], 'products.json')
    last_uploaded_file = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], 'products.last_uploaded.json')

    loaded_products = None
    for candidate_file in [products_file, last_uploaded_file]:
        if not os.path.exists(candidate_file):
            continue

        try:
            with open(candidate_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue

        if isinstance(data, list) and data:
            loaded_products = data
            if candidate_file == last_uploaded_file and candidate_file != products_file:
                os.makedirs(os.path.dirname(products_file), exist_ok=True)
                with open(products_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            break

    if not loaded_products:
        products_data = None
        products_data_source = 'none'
        matcher = None
        return False

    prepared_products = _prepare_products_for_runtime(loaded_products, source='loaded')
    return _set_runtime_products_snapshot(prepared_products, source='legacy_json')




def _safe_float(value, default=0.0):
    try:
        if value is None or value == '':
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default=0, min_value=None, max_value=None):
    try:
        if value is None or value == '':
            number = int(default)
        else:
            number = int(value)
    except (TypeError, ValueError):
        number = int(default)

    if min_value is not None:
        number = max(int(min_value), number)
    if max_value is not None:
        number = min(int(max_value), number)
    return number


def _safe_optional_float(value):
    try:
        if value is None or value == '':
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_text_value(value):
    text = str(value or '').strip()
    if not text:
        return ''
    return re.sub(r'\s+', ' ', html.unescape(text))


def _normalize_category_display_value(value):
    text = _normalize_text_value(value)
    if not text:
        return ''
    return text.replace('\u03be', ' / ')


def _extract_intro_text(intro_html):
    text = _normalize_text_value(re.sub(r'<[^>]+>', ' ', html.unescape(str(intro_html or ''))))
    return text


def _normalize_cost_price_value(value):
    if value is None or value == '':
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    try:
        return float(value)
    except (TypeError, ValueError):
        text = str(value).strip().replace(',', '')
        if not text:
            return None
        try:
            return float(text)
        except (TypeError, ValueError):
            return None


def _annotate_product_cost_fields(product, source='loaded'):
    normalized_product = dict(product or {})
    if 'category' in normalized_product:
        normalized_product['category'] = _normalize_category_display_value(normalized_product.get('category'))
    normalized_cost = _normalize_cost_price_value(normalized_product.get('cost_price'))
    has_explicit_flags = any(key in normalized_product for key in ('has_cost_price', 'cost_price_missing', 'cost_price_ambiguous'))

    if has_explicit_flags:
        cost_price_missing = bool(normalized_product.get('cost_price_missing'))
        cost_price_ambiguous = bool(normalized_product.get('cost_price_ambiguous'))
        has_cost_price = bool(normalized_product.get('has_cost_price'))

        if cost_price_missing or normalized_cost is None:
            normalized_cost = None
            has_cost_price = False
            cost_price_missing = True
            cost_price_ambiguous = False
        elif cost_price_ambiguous:
            has_cost_price = False
            cost_price_missing = False
        else:
            has_cost_price = True
            cost_price_missing = False
            cost_price_ambiguous = False
    else:
        if normalized_cost is None:
            has_cost_price = False
            cost_price_missing = True
            cost_price_ambiguous = False
        elif source == 'uploaded':
            has_cost_price = True
            cost_price_missing = False
            cost_price_ambiguous = False
        elif normalized_cost == 0:
            has_cost_price = False
            cost_price_missing = False
            cost_price_ambiguous = True
        else:
            has_cost_price = True
            cost_price_missing = False
            cost_price_ambiguous = False

    normalized_product['cost_price'] = normalized_cost
    normalized_product['has_cost_price'] = has_cost_price
    normalized_product['cost_price_missing'] = cost_price_missing
    normalized_product['cost_price_ambiguous'] = cost_price_ambiguous
    return normalized_product


def _prepare_products_for_runtime(products, source='loaded'):
    return ProductImageHandler.enrich_products_with_images([
        _annotate_product_cost_fields(product, source=source)
        for product in (products or [])
    ])


def _build_product_catalog_item(product, index=0, include_raw=False):
    product = _annotate_product_cost_fields(product, source='loaded')
    intro_html = str(product.get('intro') or '')
    images = ProductImageHandler.get_proxy_images(product, max_images=8)
    primary_image = images[0] if images else {}
    cost_price = _safe_optional_float(product.get('cost_price'))

    normalized = {
        'index': index,
        'code': _normalize_text_value(product.get('code')),
        'name': _normalize_text_value(product.get('name')),
        'model': _normalize_text_value(product.get('model')),
        'category': _normalize_text_value(product.get('category')),
        'unit': _normalize_text_value(product.get('unit')),
        'brand': _normalize_text_value(product.get('brand')),
        'supplier': _normalize_text_value(product.get('supplier')),
        'status': _normalize_text_value(product.get('status')),
        'intro': intro_html,
        'intro_html': html.unescape(intro_html),
        'intro_text': _extract_intro_text(intro_html),
        'market_price': _safe_optional_float(product.get('market_price')),
        'cost_price': cost_price,
        'product_id': _normalize_text_value(product.get('product_id')),
        'image_url': _normalize_text_value(primary_image.get('url') or product.get('image_url')),
        'source_image_url': _normalize_text_value(primary_image.get('source_url') or product.get('source_image_url')),
        'images': images,
        'has_cost_price': bool(product.get('has_cost_price')),
        'cost_price_missing': bool(product.get('cost_price_missing')),
        'cost_price_ambiguous': bool(product.get('cost_price_ambiguous'))
    }
    image_count = len(normalized['images']) if isinstance(normalized['images'], list) else 0
    normalized['image_count'] = image_count
    normalized['has_image'] = bool(normalized['image_url'] or normalized['source_image_url'] or image_count)
    normalized['search_text'] = ' '.join([
        normalized['code'],
        normalized['name'],
        normalized['model'],
        normalized['category'],
        normalized['unit'],
        normalized['brand'],
        normalized['supplier'],
        normalized['status'],
        normalized['intro_text']
    ]).lower()

    if include_raw:
        raw_fields = {}
        for key, value in (product or {}).items():
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            if isinstance(value, list) and not value:
                continue
            raw_fields[key] = value
        normalized['raw_fields'] = raw_fields

    return normalized


def _filter_catalog_products(keyword='', category='', supplier='', brand='', has_image='', page=1, page_size=24):
    global products_data

    if not products_data:
        return [], 0, 0, 1, 1

    keyword = str(keyword or '').strip().lower()
    category = str(category or '').strip()
    supplier = str(supplier or '').strip()
    brand = str(brand or '').strip()
    has_image = str(has_image or '').strip().lower()
    page = max(int(page or 1), 1)
    page_size = max(1, min(int(page_size or 24), 100))
    items = []

    for index, product in enumerate(products_data):
        item = _build_product_catalog_item(product, index=index)

        if keyword and keyword not in item['search_text']:
            continue
        if category and item['category'] != category:
            continue
        if supplier and item['supplier'] != supplier:
            continue
        if brand and item['brand'] != brand:
            continue
        if has_image == 'yes' and not item['has_image']:
            continue
        if has_image == 'no' and item['has_image']:
            continue

        items.append(item)

    total = len(items)
    image_total = sum(1 for item in items if item['has_image'])
    total_pages = max(1, math.ceil(total / page_size)) if total else 1
    page = min(page, total_pages)
    start = (page - 1) * page_size
    end = start + page_size
    return items[start:end], total, image_total, page, total_pages


def _get_catalog_filter_options():
    global products_data

    categories = []
    suppliers = []
    brands = []
    category_seen = set()
    supplier_seen = set()
    brand_seen = set()

    for product in products_data or []:
        category = _normalize_text_value(product.get('category'))
        supplier = _normalize_text_value(product.get('supplier'))
        brand = _normalize_text_value(product.get('brand'))
        if category and category not in category_seen:
            category_seen.add(category)
            categories.append(category)
        if supplier and supplier not in supplier_seen:
            supplier_seen.add(supplier)
            suppliers.append(supplier)
        if brand and brand not in brand_seen:
            brand_seen.add(brand)
            brands.append(brand)

    categories.sort()
    suppliers.sort()
    brands.sort()
    return categories, suppliers, brands


def _pick_cost_price(row):
    for field_name in ['成本价', '采购价', '进货价', '参考成本价', '* 成本价', '* 采购价', '* 进货价']:
        if field_name in row and not pd.isna(row.get(field_name)):
            value = _normalize_cost_price_value(row.get(field_name))
            if value is not None:
                return value
    return None


def _serialize_catalog_field_value(value):
    if value is None:
        return ''
    if isinstance(value, bool):
        return '是' if value else '否'
    if isinstance(value, (int, float)):
        try:
            if pd.isna(value):
                return ''
        except Exception:
            pass
        return str(value)
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    return _normalize_text_value(value)


def _build_catalog_detail_fields(product):
    product = _annotate_product_cost_fields(product, source='loaded')
    preferred_fields = [
        ('商品编码', product.get('code')),
        ('商品名称', product.get('name')),
        ('型号', product.get('model')),
        ('品牌', product.get('brand')),
        ('商品类别', product.get('category')),
        ('单位', product.get('unit')),
        ('所属供应商', product.get('supplier')),
        ('状态', product.get('status')),
        ('商品ID', product.get('product_id')),
    ]

    detail_fields = []
    seen_labels = set()
    for label, value in preferred_fields:
        serialized = _serialize_catalog_field_value(value)
        if not serialized:
            continue
        detail_fields.append({'label': label, 'value': serialized})
        seen_labels.add(label)

    skip_keys = {
        'intro',
        'images',
        'image_url',
        'source_image_url',
        'search_text',
        'has_cost_price',
        'cost_price_missing',
        'cost_price_ambiguous',
        'has_image',
        'image_count'
    }
    label_map = {
        'code': '商品编码',
        'name': '商品名称',
        'model': '型号',
        'brand': '品牌',
        'category': '商品类别',
        'unit': '单位',
        'supplier': '所属供应商',
        'status': '状态',
        'product_id': '商品ID',
        'market_price': '市场价',
        'cost_price': '成本价'
    }

    for key, value in (product or {}).items():
        if key in skip_keys:
            continue
        label = label_map.get(key, key)
        if label in seen_labels:
            continue

        if key == 'cost_price':
            if product.get('cost_price_missing'):
                serialized = '未导入'
            elif product.get('cost_price_ambiguous'):
                serialized = '历史数据待校正'
            else:
                serialized = _serialize_catalog_field_value(value)
        else:
            serialized = _serialize_catalog_field_value(value)

        if not serialized:
            continue
        detail_fields.append({'label': label, 'value': serialized})
        seen_labels.add(label)

    return detail_fields


def _build_catalog_product_detail(product, index=0):
    ProductImageHandler.ensure_product_metadata(product)
    detail = _build_product_catalog_item(product, index=index, include_raw=True)
    detail['detail_fields'] = _build_catalog_detail_fields(product)
    return detail


def _find_catalog_product_index(product_code):
    if not products_data:
        return -1
    product_code = str(product_code or '').strip()
    for index, product in enumerate(products_data):
        if str(product.get('code', '') or '').strip() == product_code:
            return index
    return -1


def _update_parse_result_template_match(parse_result):
    if not parse_result:
        return parse_result
    templates = load_templates().get('templates', [])
    matched_template = SmartQuoteParser.match_template_for_result(parse_result, templates)
    updated = dict(parse_result)
    updated['matched_template'] = matched_template
    return updated


def _upsert_learned_template(parse_result, confirmed_mapping, source_type='excel', manual_save=False):
    parse_result = SmartQuoteParser.apply_template_learning_to_result(parse_result or {}, confirmed_mapping, source_type=source_type)
    templates_data = load_templates()
    templates = templates_data.setdefault('templates', [])
    matched_template = parse_result.get('matched_template') or {}
    matched_template_name = matched_template.get('name', '')
    template_hit = bool(matched_template_name)

    updated_template = None
    previous_mapping = (matched_template or {}).get('last_confirmed_mapping') or (matched_template or {}).get('column_mapping') or {}
    if matched_template_name:
        for idx, template in enumerate(templates):
            if template.get('name') == matched_template_name:
                previous_mapping = template.get('last_confirmed_mapping') or template.get('column_mapping') or previous_mapping
                updated_template = SmartQuoteParser.register_template_usage_for_result(
                    template,
                    parse_result,
                    confirmed_mapping,
                    source_type=source_type,
                    manual_save=manual_save,
                    template_hit=template_hit
                )
                templates[idx] = updated_template
                break

    if updated_template is None:
        template_name = matched_template_name or f"自动学习模板-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        updated_template = SmartQuoteParser.build_template_payload_from_result(
            parse_result,
            template_name,
            confirmed_mapping,
            source_type=source_type,
            manual_save=manual_save,
            template_hit=template_hit,
            previous_mapping=previous_mapping
        )
        templates.append(updated_template)

    save_templates(templates_data)
    parse_result['matched_template'] = updated_template
    parse_result['mapping_changed'] = bool(updated_template.get('last_mapping_changed'))
    parse_result['mapping_signature'] = updated_template.get('mapping_signature', '')
    return parse_result, updated_template


def _get_refreshed_parse_result_cache():
    global parse_result_cache
    if parse_result_cache:
        parse_result_cache = _update_parse_result_template_match(parse_result_cache)
    return parse_result_cache


def _enrich_quote_items(items, source_type, mapping_changed=False, mapping_signature=''):
    enriched = [normalize_quote_item(item) for item in items]
    for item in enriched:
        item['source_type'] = source_type
        item['mapping_changed'] = bool(mapping_changed)
        item['mapping_signature'] = mapping_signature or build_mapping_signature(item)
    return enriched


def _rebuild_match_results(items, source_type, template_name='', template_hit=False, mapping_changed=False, mapping_signature=''):
    global match_results
    if matcher is None:
        if not load_products():
            raise ValueError('请先导入商品库！')
    synonyms = load_synonyms()
    current_match_context['source_type'] = source_type
    current_match_context['template_name'] = template_name
    current_match_context['template_hit'] = template_hit
    current_match_context['mapping_changed'] = bool(mapping_changed)
    current_match_context['mapping_signature'] = mapping_signature or ''
    match_results = match_quote_items(items, synonyms)
    return match_results


def _save_match_feedback(item_index, result_row, selected_product, action):
    if quote_db is None:
        return
    query_item = result_row.get('query_item') or (quote_items[item_index] if item_index < len(quote_items) else {})
    payload = get_match_feedback_payload(
        query_item={
            **(query_item or {}),
            'mapping_changed': current_match_context.get('mapping_changed', False),
            'mapping_signature': current_match_context.get('mapping_signature', '') or query_item.get('mapping_signature', '')
        },
        result_row=result_row,
        selected_product=selected_product,
        action=action,
        source_type=current_match_context.get('source_type', ''),
        template_name=current_match_context.get('template_name', ''),
        template_hit=current_match_context.get('template_hit', False)
    )
    quote_db.save_match_feedback(payload)


def _relearn_after_confirmation(item_index):
    global match_results
    if matcher is None or item_index < 0 or item_index >= len(match_results):
        return
    result_row = match_results[item_index]
    query_item = result_row.get('query_item') or {}
    refreshed_matches = matcher.match_single(query_item, load_synonyms(), feedback_provider=get_match_feedback_rows)
    result_row['matches'] = refreshed_matches
    result_row['best_match'] = refreshed_matches[0] if refreshed_matches else None


def _build_catalog_response(keyword='', category='', supplier='', brand='', has_image='', page=1, page_size=24):
    items, total, image_total, current_page, total_pages = _filter_catalog_products(
        keyword=keyword,
        category=category,
        supplier=supplier,
        brand=brand,
        has_image=has_image,
        page=page,
        page_size=page_size
    )
    categories, suppliers, brands = _get_catalog_filter_options()
    return {
        'success': True,
        'items': items,
        'total': total,
        'page': current_page,
        'page_size': page_size,
        'total_pages': total_pages,
        'image_total': image_total,
        'loaded': products_data is not None,
        'filters': {
            'categories': categories,
            'suppliers': suppliers,
            'brands': brands
        }
    }


def _build_catalog_detail_response(product_code):
    product = _find_catalog_product_by_code(product_code)
    if not product:
        return None

    product_index = _find_catalog_product_index(product_code)
    detail = _build_catalog_product_detail(product, index=product_index if product_index >= 0 else 0)
    detail['images'] = ProductImageHandler.get_proxy_images(product, max_images=8)
    if detail['images']:
        detail['image_url'] = detail['images'][0].get('url', '') or detail.get('image_url', '')
        detail['source_image_url'] = detail['images'][0].get('source_url', '') or detail.get('source_image_url', '')
    detail['has_image'] = bool(detail['images'] or detail.get('image_url') or detail.get('source_image_url'))
    detail['image_count'] = len(detail['images'])
    return detail


def _normalize_image_search_product_item(candidate):
    product_code = _normalize_text_value(candidate.product_code)
    image_url = f"/api/catalog/image_asset/{candidate.asset_id}/file"
    similarity = max(0.0, min(1.0, float(candidate.similarity or 0.0)))
    base_similarity = candidate.base_similarity
    rerank_score = candidate.rerank_score

    return {
        'index': int(candidate.product_id or 0),
        'code': product_code,
        'name': _normalize_text_value(candidate.product_name),
        'model': _normalize_text_value(candidate.variant_name),
        'category': _normalize_text_value(candidate.category_name),
        'unit': '',
        'brand': _normalize_text_value(candidate.brand_name),
        'supplier': '',
        'status': 'active',
        'intro': '',
        'intro_html': '',
        'intro_text': '',
        'market_price': float(candidate.reference_price) if candidate.reference_price is not None else None,
        'cost_price': None,
        'product_id': str(candidate.product_id or ''),
        'image_url': image_url,
        'source_image_url': _normalize_text_value(candidate.resolved_url) or image_url,
        'images': [{
            'title': _normalize_text_value(candidate.product_name) or '图片检索结果',
            'thumb': image_url,
            'source_url': _normalize_text_value(candidate.resolved_url) or image_url,
            'url': image_url,
            'proxy_url': image_url,
            'product_id': str(candidate.product_id or '')
        }],
        'image_count': 1,
        'has_image': True,
        'catalog_score': round(similarity * 100),
        'image_similarity': similarity,
        'image_distance': float(candidate.distance or 0.0),
        'asset_id': int(candidate.asset_id),
        'search_type': 'image',
        'archive_file_url': image_url,
        'resolved_url': _normalize_text_value(candidate.resolved_url),
        'source_url': _normalize_text_value(candidate.source_url),
        'mime_type': _normalize_text_value(candidate.mime_type),
        'width': candidate.width,
        'height': candidate.height,
        'base_similarity': float(base_similarity) if base_similarity is not None else None,
        'rerank_score': float(rerank_score) if rerank_score is not None else None,
        'rerank_reason': _normalize_text_value(candidate.rerank_reason),
        'search_text': ' '.join(filter(None, [
            _normalize_text_value(candidate.product_code),
            _normalize_text_value(candidate.product_name),
            _normalize_text_value(candidate.variant_name),
            _normalize_text_value(candidate.brand_name),
            _normalize_text_value(candidate.category_name),
        ])).lower()
    }


def _normalize_v2_status_text(status: str | None) -> str:
    status_text = _normalize_text_value(status)
    if status_text == 'active':
        return '上架'
    if status_text == 'inactive':
        return '下架'
    return status_text or '未知'


def _extract_v2_intro_payload(product) -> tuple[str, str]:
    payload = getattr(product, 'source_payload', None) or {}
    legacy_intro_text = _normalize_text_value(payload.get('legacy_intro_text'))
    legacy_row = payload.get('legacy_row') or {}
    intro_html = _normalize_text_value(legacy_row.get('intro'))
    return intro_html or '', legacy_intro_text or ''


def _build_v2_product_images(product, max_images=8):
    images = []
    product_images = list(getattr(product, 'images', []) or [])
    product_images.sort(key=lambda item: (not bool(getattr(item, 'is_primary', False)), int(getattr(item, 'sort_order', 0) or 0), int(getattr(item, 'id', 0) or 0)))
    for product_image in product_images[:max_images]:
        asset_id = getattr(product_image, 'asset_id', None)
        proxy_url = f"/api/catalog/image_asset/{asset_id}/file" if asset_id else ''
        source_url = _normalize_text_value(getattr(product_image, 'resolved_url', None)) or _normalize_text_value(getattr(product_image, 'source_url', None)) or proxy_url
        image_url = proxy_url or source_url
        if not image_url:
            continue
        images.append({
            'title': _normalize_text_value(getattr(product, 'name', None)) or '商品图片',
            'thumb': image_url,
            'source_url': source_url,
            'url': image_url,
            'proxy_url': proxy_url or image_url,
            'product_id': str(getattr(product, 'id', '') or '')
        })
    return images


def _normalize_v2_catalog_product_item(product, index=0, include_raw=False):
    intro_html, intro_text = _extract_v2_intro_payload(product)
    variants = list(getattr(product, 'variants', []) or [])
    variants.sort(key=lambda item: int(getattr(item, 'id', 0) or 0))
    primary_variant = variants[0] if variants else None
    images = _build_v2_product_images(product)
    first_image = images[0] if images else {}
    category_obj = getattr(product, 'category', None)
    category_text = _normalize_text_value(getattr(category_obj, 'path', None)) or _normalize_text_value(getattr(category_obj, 'name', None))
    if category_text:
        category_text = category_text.replace('\u03be', ' / ')

    item = {
        'index': index,
        'code': _normalize_text_value(getattr(product, 'product_code', None)) or _normalize_text_value(getattr(product, 'external_product_id', None)),
        'name': _normalize_text_value(getattr(product, 'name', None)),
        'model': _normalize_text_value(getattr(primary_variant, 'variant_name', None)) or _normalize_text_value(getattr(primary_variant, 'spec_text', None)),
        'category': category_text or '',
        'unit': _normalize_text_value(getattr(product, 'unit', None)),
        'market_price': float(getattr(primary_variant, 'sale_price', None) or getattr(product, 'reference_price', None) or 0) if (getattr(primary_variant, 'sale_price', None) is not None or getattr(product, 'reference_price', None) is not None) else None,
        'cost_price': float(getattr(primary_variant, 'cost_price', None)) if getattr(primary_variant, 'cost_price', None) is not None else None,
        'brand': _normalize_text_value(getattr(getattr(product, 'brand', None), 'name', None)),
        'supplier': _normalize_text_value(getattr(getattr(product, 'supplier', None), 'name', None)),
        'status': _normalize_v2_status_text(getattr(product, 'status', None)),
        'intro': intro_html,
        'intro_html': intro_html,
        'intro_text': intro_text,
        'product_id': str(getattr(product, 'id', '') or ''),
        'image_url': first_image.get('url', '') or '',
        'source_image_url': first_image.get('source_url', '') or '',
        'images': images,
        'image_count': len(images),
        'has_image': bool(images),
        'search_text': _normalize_text_value(getattr(product, 'search_text', None)) or ' '.join(filter(None, [
            _normalize_text_value(getattr(product, 'product_code', None)),
            _normalize_text_value(getattr(product, 'name', None)),
            _normalize_text_value(getattr(primary_variant, 'variant_name', None)),
            _normalize_text_value(getattr(getattr(product, 'brand', None), 'name', None)),
            category_text,
            intro_text,
        ])).lower(),
        'source': 'postgres_v2',
    }
    item = _annotate_product_cost_fields(item, source='loaded')
    if include_raw:
        item['raw_fields'] = {
            'source_type': _normalize_text_value(getattr(product, 'source_type', None)),
            'status': _normalize_text_value(getattr(product, 'status', None)),
            'last_synced_at': getattr(product, 'last_synced_at', None).isoformat() if getattr(product, 'last_synced_at', None) else '',
        }
    return item


def _to_v2_category_filter_value(value: str | None) -> str:
    normalized = _normalize_text_value(value)
    if not normalized:
        return ''
    return re.sub(r'\s*/\s*', '\u03be', normalized)


def _to_catalog_category_display(value: str | None) -> str:
    normalized = _normalize_text_value(value)
    if not normalized:
        return ''
    return normalized.replace('\u03be', ' / ')


async def _get_v2_catalog_filter_options_async(session):
    categories = []
    suppliers = []
    brands = []
    category_seen = set()
    supplier_seen = set()
    brand_seen = set()

    category_rows = (
        await session.execute(
            sa_select(V2Category.path, V2Category.name)
            .join(V2Product, V2Product.category_id == V2Category.id)
            .distinct()
            .order_by(V2Category.path, V2Category.name)
        )
    ).all()
    for row in category_rows:
        category_value = _to_catalog_category_display(row.path or row.name)
        if category_value and category_value not in category_seen:
            category_seen.add(category_value)
            categories.append(category_value)

    brand_rows = (
        await session.scalars(
            sa_select(V2Brand.name)
            .join(V2Product, V2Product.brand_id == V2Brand.id)
            .where(V2Brand.name.is_not(None))
            .distinct()
            .order_by(V2Brand.name)
        )
    ).all()
    for brand_name in brand_rows:
        brand_value = _normalize_text_value(brand_name)
        if brand_value and brand_value not in brand_seen:
            brand_seen.add(brand_value)
            brands.append(brand_value)

    supplier_rows = (
        await session.scalars(
            sa_select(V2Supplier.name)
            .join(V2Product, V2Product.supplier_id == V2Supplier.id)
            .where(V2Supplier.name.is_not(None))
            .distinct()
            .order_by(V2Supplier.name)
        )
    ).all()
    for supplier_name in supplier_rows:
        supplier_value = _normalize_text_value(supplier_name)
        if supplier_value and supplier_value not in supplier_seen:
            supplier_seen.add(supplier_value)
            suppliers.append(supplier_value)

    return categories, suppliers, brands


async def _build_v2_catalog_response_async(keyword='', category='', supplier='', brand='', has_image='', page=1, page_size=24):
    if not V2_CATALOG_AVAILABLE:
        raise RuntimeError(f'V2 商品库不可用：{V2_CATALOG_IMPORT_ERROR or "依赖未安装"}')

    keyword = _normalize_text_value(keyword)
    category = _normalize_text_value(category)
    supplier = _normalize_text_value(supplier)
    brand = _normalize_text_value(brand)
    has_image = str(has_image or '').strip().lower()
    page = max(int(page or 1), 1)
    page_size = max(1, min(int(page_size or 24), 100))
    category_path = _to_v2_category_filter_value(category)
    image_product_ids_stmt = sa_select(V2ProductImage.product_id).where(V2ProductImage.product_id.is_not(None))
    product_has_image_clause = or_(
        V2Product.primary_image_url.is_not(None),
        V2Product.id.in_(image_product_ids_stmt),
    )

    async with V2AsyncSessionLocal() as session:
        base_ids_stmt = (
            sa_select(V2Product.id)
            .select_from(V2Product)
            .outerjoin(V2Brand, V2Brand.id == V2Product.brand_id)
            .outerjoin(V2Category, V2Category.id == V2Product.category_id)
            .outerjoin(V2Supplier, V2Supplier.id == V2Product.supplier_id)
            .outerjoin(V2ProductVariant, V2ProductVariant.product_id == V2Product.id)
        )

        if keyword:
            like_value = f'%{keyword}%'
            base_ids_stmt = base_ids_stmt.where(
                or_(
                    V2Product.name.ilike(like_value),
                    V2Product.product_code.ilike(like_value),
                    V2Product.external_product_id.ilike(like_value),
                    V2Product.search_text.ilike(like_value),
                    V2ProductVariant.variant_name.ilike(like_value),
                    V2ProductVariant.spec_text.ilike(like_value),
                    V2Brand.name.ilike(like_value),
                    V2Supplier.name.ilike(like_value),
                    V2Category.name.ilike(like_value),
                    V2Category.path.ilike(like_value),
                )
            )

        if category:
            base_ids_stmt = base_ids_stmt.where(
                or_(
                    V2Category.path == category_path,
                    V2Category.name == category,
                )
            )

        if supplier:
            base_ids_stmt = base_ids_stmt.where(V2Supplier.name == supplier)

        if brand:
            base_ids_stmt = base_ids_stmt.where(V2Brand.name == brand)

        if has_image == 'yes':
            base_ids_stmt = base_ids_stmt.where(product_has_image_clause)
        elif has_image == 'no':
            base_ids_stmt = (
                base_ids_stmt
                .where(V2Product.primary_image_url.is_(None))
                .where(~V2Product.id.in_(image_product_ids_stmt))
            )

        total = int(
            await session.scalar(
                sa_select(sa_func.count()).select_from(base_ids_stmt.distinct().subquery())
            ) or 0
        )
        total_pages = max(1, math.ceil(total / page_size)) if total else 1
        current_page = min(page, total_pages) if total else 1
        offset = (current_page - 1) * page_size

        paged_rows = (
            await session.execute(
                base_ids_stmt
                .with_only_columns(V2Product.id, product_has_image_clause.label('has_image'))
                .distinct()
                .order_by(product_has_image_clause.desc(), V2Product.id.desc())
                .offset(offset)
                .limit(page_size)
            )
        )
        paged_ids = [row[0] for row in paged_rows.all()]

        if has_image == 'yes':
            image_total = total
        elif has_image == 'no':
            image_total = 0
        else:
            image_total = int(
                await session.scalar(
                    sa_select(sa_func.count()).select_from(
                        base_ids_stmt.where(product_has_image_clause).distinct().subquery()
                    )
                ) or 0
            )

        categories, suppliers, brands = await _get_v2_catalog_filter_options_async(session)

        items = []
        if paged_ids:
            products = list(
                (
                    await session.scalars(
                        sa_select(V2Product)
                        .options(
                            selectinload(V2Product.brand),
                            selectinload(V2Product.category),
                            selectinload(V2Product.supplier),
                            selectinload(V2Product.variants),
                            selectinload(V2Product.images),
                        )
                        .where(V2Product.id.in_(paged_ids))
                    )
                ).all()
            )
            order_map = {product_id: index for index, product_id in enumerate(paged_ids)}
            products.sort(key=lambda product: order_map.get(getattr(product, 'id', 0), 10**9))

            for index, product in enumerate(products, start=offset):
                item = _normalize_v2_catalog_product_item(product, index=index)
                item['catalog_source'] = 'postgres_v2'
                items.append(item)

        return {
            'success': True,
            'items': items,
            'total': total,
            'page': current_page,
            'page_size': page_size,
            'total_pages': total_pages,
            'image_total': image_total,
            'loaded': True,
            'catalog_source': 'postgres_v2',
            'filters': {
                'categories': categories,
                'suppliers': suppliers,
                'brands': brands,
            }
        }


async def _load_v2_product_by_code_async(product_code):
    if not V2_CATALOG_AVAILABLE:
        return None

    product_code = _normalize_text_value(product_code)
    if not product_code:
        return None

    async with V2AsyncSessionLocal() as session:
        return await session.scalar(
            sa_select(V2Product)
            .options(
                selectinload(V2Product.brand),
                selectinload(V2Product.category),
                selectinload(V2Product.supplier),
                selectinload(V2Product.variants),
                selectinload(V2Product.images),
            )
            .where(
                or_(
                    V2Product.product_code == product_code,
                    V2Product.external_product_id == product_code,
                )
            )
            .limit(1)
        )


async def _build_v2_catalog_detail_response_async(product_code):
    product = await _load_v2_product_by_code_async(product_code)
    if not product:
        return None
    detail = _normalize_v2_catalog_product_item(product, include_raw=True)
    detail['detail_fields'] = _build_catalog_detail_fields(detail)
    detail['has_image'] = bool(detail.get('images') or detail.get('image_url') or detail.get('source_image_url'))
    detail['image_count'] = len(detail.get('images') or [])
    return detail


def _score_catalog_candidate(item, search_terms, normalized_item):
    item_text = str(item.get('search_text') or '').lower()
    score = 0

    for term in search_terms:
        lowered = str(term or '').strip().lower()
        if not lowered:
            continue
        if str(item.get('name') or '').lower() == lowered:
            score += 120
        elif lowered in str(item.get('name') or '').lower():
            score += 70
        if item.get('model') and lowered in str(item.get('model') or '').lower():
            score += 40
        if item.get('code') and lowered in str(item.get('code') or '').lower():
            score += 80
        if lowered in item_text:
            score += 15

    if normalized_item.get('normalized_unit') and normalized_item['normalized_unit'] == item.get('unit'):
        score += 10

    return score


async def _search_v2_catalog_for_quote_async(keyword, search_terms, normalized_item, limit=20):
    if not V2_CATALOG_AVAILABLE:
        return []

    clauses = []
    for term in search_terms:
        value = _normalize_text_value(term)
        if not value:
            continue
        like_value = f"%{value}%"
        clauses.extend([
            V2Product.name.ilike(like_value),
            V2Product.product_code.ilike(like_value),
            V2Product.external_product_id.ilike(like_value),
            V2Product.search_text.ilike(like_value),
            V2ProductVariant.variant_name.ilike(like_value),
            V2ProductVariant.spec_text.ilike(like_value),
        ])

    if not clauses:
        return []

    async with V2AsyncSessionLocal() as session:
        product_ids = list((await session.scalars(
            sa_select(V2Product.id)
            .outerjoin(V2ProductVariant, V2ProductVariant.product_id == V2Product.id)
            .where(or_(*clauses))
            .distinct()
            .limit(max(limit * 6, 80))
        )).all())
        if not product_ids:
            return []

        products = list((await session.scalars(
            sa_select(V2Product)
            .options(
                selectinload(V2Product.brand),
                selectinload(V2Product.category),
                selectinload(V2Product.supplier),
                selectinload(V2Product.variants),
                selectinload(V2Product.images),
            )
            .where(V2Product.id.in_(product_ids))
        )).all())

    items = []
    seen_codes = set()
    for product in products:
        item = _normalize_v2_catalog_product_item(product)
        score = _score_catalog_candidate(item, search_terms, normalized_item)
        if score <= 0:
            continue
        code_key = item['code'] or f"__idx_{item['index']}"
        if code_key in seen_codes:
            continue
        seen_codes.add(code_key)
        item['catalog_score'] = score
        item['catalog_source'] = 'postgres_v2'
        items.append(item)

    items.sort(key=lambda x: (x.get('catalog_score', 0), x.get('has_image', False), x.get('market_price', 0) or 0), reverse=True)
    return items[:limit]


async def _get_v2_catalog_sync_status_async():
    if not V2_CATALOG_AVAILABLE:
        return {
            'success': False,
            'message': f'V2 商品同步不可用：{V2_CATALOG_IMPORT_ERROR or "依赖未安装"}',
        }
    async with V2AsyncSessionLocal() as session:
        job = await v2_get_latest_catalog_sync_job(session)
        product_count = await session.scalar(sa_select(sa_func.count()).select_from(V2Product))
        return {
            'success': True,
            'job': v2_build_sync_job_summary(job),
            'product_count': int(product_count or 0),
        }


async def _run_v2_catalog_manual_sync_async(requested_by='flask-workbench'):
    if not V2_CATALOG_AVAILABLE:
        raise RuntimeError(f'V2 商品同步不可用：{V2_CATALOG_IMPORT_ERROR or "依赖未安装"}')
    async with V2AsyncSessionLocal() as session:
        service = V2LegacyCatalogSyncService(
            session,
            dry_run=False,
            source_type='legacy_json_upload',
            source_name='products_json_manual',
            requested_by=requested_by,
        )
        result = await service.run_from_default_file()
        return result


async def _run_v2_catalog_items_sync_async(items, requested_by='flask-upload-products', source_name='products_upload_inline'):
    if not V2_CATALOG_AVAILABLE:
        raise RuntimeError(f'V2 商品同步不可用：{V2_CATALOG_IMPORT_ERROR or "依赖未安装"}')

    normalized_items = [dict(item or {}) for item in (items or [])]
    async with V2AsyncSessionLocal() as session:
        service = V2LegacyCatalogSyncService(
            session,
            dry_run=False,
            source_type='legacy_json_upload',
            source_name=source_name,
            requested_by=requested_by,
        )
        return await service.run_items(normalized_items)


async def _run_v2_catalog_mall_scrape_sync_async(requested_by='flask-mall-scrape', options=None, dry_run=False):
    if not V2_CATALOG_AVAILABLE:
        raise RuntimeError(f'V2 商品同步不可用：{V2_CATALOG_IMPORT_ERROR or "依赖未安装"}')

    return await v2_run_mall_scrape_sync_async(
        requested_by=requested_by,
        options=options or {},
        dry_run=dry_run,
    )


def _normalize_image_search_provider(provider='', model_name=''):
    provider = _normalize_text_value(provider) or V2_IMAGE_EMBEDDING_PROVIDER
    model_name = _normalize_text_value(model_name) or ''

    if provider == V2_CLIP_EMBEDDING_PROVIDER:
        return V2_CLIP_EMBEDDING_PROVIDER, model_name or V2_CLIP_EMBEDDING_MODEL_NAME

    return V2_IMAGE_EMBEDDING_PROVIDER, model_name or V2_IMAGE_EMBEDDING_MODEL_NAME


async def _search_catalog_by_image_async(file_bytes, top_k=12, query_text='', spec_hint='', brand_hint='', provider='', model_name=''):
    if not V2_IMAGE_SEARCH_AVAILABLE:
        raise RuntimeError(f'V2图搜图模块不可用: {V2_IMAGE_SEARCH_IMPORT_ERROR or "未安装依赖"}')

    provider, model_name = _normalize_image_search_provider(provider, model_name)
    async with V2AsyncSessionLocal() as session:
        query_features = v2_compute_query_image_features_for_provider(
            file_bytes,
            provider=provider,
            model_name=model_name,
        )
        candidates = await v2_search_similar_products(
            session,
            query_vector=query_features.vector,
            top_k=top_k,
            provider=provider,
            model_name=model_name,
            query_text=query_text,
            spec_hint=spec_hint,
            brand_hint=brand_hint,
        )
        items = [_normalize_image_search_product_item(candidate) for candidate in candidates]
        return {
            'provider': provider,
            'model_name': model_name,
            'vector_dim': len(query_features.vector) or V2_IMAGE_EMBEDDING_VECTOR_DIM,
            'query_phash': query_features.phash,
            'query_dhash': query_features.dhash,
            'query_width': query_features.width,
            'query_height': query_features.height,
            'items': items,
            'total': len(items)
        }


async def _get_v2_image_embedding_status_async():
    if not V2_IMAGE_SEARCH_AVAILABLE:
        raise RuntimeError(f'V2图搜图模块不可用: {V2_IMAGE_SEARCH_IMPORT_ERROR or "未安装依赖"}')
    async with V2AsyncSessionLocal() as session:
        providers = await v2_get_image_embedding_status(session)
        return {
            'provider': V2_IMAGE_EMBEDDING_PROVIDER,
            'model_name': V2_IMAGE_EMBEDDING_MODEL_NAME,
            'vector_dim': V2_IMAGE_EMBEDDING_VECTOR_DIM,
            'providers': [
                {
                    'provider': item.provider,
                    'model_name': item.model_name,
                    'vector_dim': item.vector_dim,
                    'active': item.active,
                    'available': item.available,
                    'schema_supported': item.schema_supported,
                    'ready_embeddings': item.ready_embeddings,
                    'total_ready_assets': item.total_ready_assets,
                    'pending_assets': item.pending_assets,
                    'missing_dependency': item.missing_dependency,
                    'note': item.note,
                }
                for item in providers
            ],
        }


def _prepare_ocr_parse_result(parsed_items, raw_text):
    parse_result = build_ocr_parse_result(parsed_items, raw_text)
    return _update_parse_result_template_match(parse_result)


def _find_catalog_product_by_code(product_code):
    if not products_data:
        return None
    return ProductImageHandler.find_product_by_code(products_data, product_code)


def load_synonyms():
    """加载同义词库"""
    synonyms_file = os.path.join(app.config['UPLOAD_FOLDER'], 'synonyms.json')
    if os.path.exists(synonyms_file):
        with open(synonyms_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def get_match_feedback_rows(query_signature: str = '', normalized_name: str = '', normalized_spec: str = '', normalized_unit: str = '', mapping_signature: str = ''):
    """查询与当前询价项相关的历史匹配反馈"""
    if quote_db is None:
        return []
    return quote_db.get_match_feedback(
        normalized_name=normalized_name,
        normalized_spec=normalized_spec,
        normalized_unit=normalized_unit,
        query_signature=query_signature,
        mapping_signature=mapping_signature,
        limit=50
    )


def match_quote_items(items, synonyms=None, use_ai=None):
    """统一执行匹配并接入历史反馈学习"""
    global matcher, products_data, ai_service, use_ai_matcher

    synonyms = synonyms or load_synonyms()
    should_use_ai = use_ai_matcher if use_ai is None else use_ai

    if AI_AVAILABLE and should_use_ai and ai_service and ai_service.is_available():
        ai_matcher = AIProductMatcher(products_data, ai_service)
        return ai_matcher.match_all(items, synonyms, feedback_provider=get_match_feedback_rows)

    return matcher.match_all(items, synonyms, feedback_provider=get_match_feedback_rows)


def save_synonyms(synonyms):
    """保存同义词库"""
    synonyms_file = os.path.join(app.config['UPLOAD_FOLDER'], 'synonyms.json')
    with open(synonyms_file, 'w', encoding='utf-8') as f:
        json.dump(synonyms, f, ensure_ascii=False, indent=2)


def _make_export_template(key, export_format, label, description, supports_price_types, source='system',
                          default=False, use_cases=None, preview_fields=None, extension_targets=None,
                          **extra):
    template = {
        'key': key,
        'export_format': export_format,
        'label': label,
        'description': description,
        'supports_price_types': supports_price_types or [],
        'default': default,
        'source': source,
        'use_cases': use_cases or [],
        'preview_fields': preview_fields or [],
        'extension_targets': extension_targets or []
    }
    template.update(extra)
    return template


MALL_TEMPLATE_CAPABILITY = {
    'doc_types': [
        {'label': '报价单', 'coverage': '已覆盖', 'highlights': ['客户报价', '总额汇总']},
        {'label': '订货单', 'coverage': '已接入', 'highlights': ['标准版', '支付二维码占位', '商品图片字段']},
        {'label': '发货单', 'coverage': '已接入', 'highlights': ['物流字段', '收货信息', '带图版']},
        {'label': '采购单', 'coverage': '已接入', 'highlights': ['供应商', '采购价', '交期']},
        {'label': '供应商订单', 'coverage': '已接入', 'highlights': ['供应商协同', '执行流转']},
        {'label': '退货 / 采购退货', 'coverage': '已接入', 'highlights': ['逆向单据', '退货原因']},
        {'label': '入库单', 'coverage': '已接入', 'highlights': ['仓储入库', '带图版']},
        {'label': '合并出库 / 合并打印', 'coverage': '已接入', 'highlights': ['批量打印', '合单输出']},
        {'label': '订单商品明细', 'coverage': '已接入', 'highlights': ['明细单独导出', '行级输出']}
    ],
    'marker_groups': [
        {
            'label': '订单属性',
            'pattern': '$OrderNo$',
            'examples': ['$OrderNo$', '$CustomerName$', '$CreateTime$']
        },
        {
            'label': '商品列表行',
            'pattern': '$#ProductName#$',
            'examples': ['$#ProductName#$', '$#UnitPrice#$', '$#ProductImg#$']
        },
        {
            'label': '图片 / 二维码',
            'pattern': '*OrderPayQRCode* / $OrderQRCode$',
            'examples': ['$#ProductImg#$', '*OrderPayQRCode*', '$OrderQRCode$']
        }
    ],
    'rules': [
        '订单属性取值标记以 $ 开头并以 $ 结尾，例如 $OrderNo$。',
        '商品列表取值标记以 $# 开头并以 #$ 结尾，整行作为商品明细行。',
        '取值标记不区分大小写，例如 $orderid$ 与 $OrderId$ 等价。',
        '同一行不要混用订单属性标记和商品列表标记。',
        '所有商品列表标记应放在同一行，便于系统按明细批量展开。'
    ],
    'recommended_features': [
        '模板变量字典中心',
        '模板能力矩阵总览',
        '模板上传后自动识别支持字段',
        '模板就绪度校验',
        '报价结果一键流转为订货 / 发货 / 采购单',
        '图片 / 二维码模板开关'
    ],
    'validator_summary': '商城模板中心现在会把主要单据作为真实导出模板展示；上传外部模板后，后续还可以继续接自动校验和字段缺口提示。',
    'validator_sections': [
        {
            'label': '必过结构',
            'items': ['至少存在 1 个订单属性标记', '至少存在 1 行商品明细标记', '商品明细标记集中在同一行', '订单属性与商品明细标记不混排']
        },
        {
            'label': '建议补齐',
            'items': ['金额汇总字段尽量成组出现', '客户 / 供应商 / 物流字段按单据方向分层补齐', '品牌、规格、单位等行级字段尽量齐全']
        },
        {
            'label': '增强能力',
            'items': ['商品图片字段', '支付二维码 / 订单二维码字段', '状态 / 仓库 / 交期等流程字段']
        }
    ],
    'validator_outputs': ['识别当前模板更像报价单 / 订货单 / 发货单 / 采购单', '给出模板就绪度分数与缺口字段', '提示可直接复用的字段组与建议新增字段', '为后续一键导出和模板学习提供结构化基础']
}


MALL_EXTENSION_HOOKS = [
    {
        'key': 'mall_order',
        'label': '订货单',
        'description': '沿用商城字段结构，把已确认报价继续转成下游订货单。',
        'status': 'ready',
        'scenario': '适合客户确认报价后，快速生成正式下单单据。',
        'inherited_fields': ['品牌', '商品名称', '规格', '数量', '备注'],
        'prerequisites': ['客户名称', '收货信息', '报价确认结果'],
        'readiness_note': '当前已可直接生成标准版、二维码版、带图版订货单；缺失页头信息时会使用可读占位。',
        'rollout_order': 1,
        'value_summary': '最适合作为第一阶段落地，因为它最直接承接当前报价结果，复用字段最多、理解成本最低。',
        'template_variants': ['商城订货单（标准版）', '商城订货单（二维码版）', '商城订货单（带图版）'],
        'field_focus': ['订单头信息', '客户与收货信息', '商品明细行', '金额汇总', '二维码 / 商品图'],
        'landing_checklist': ['确认报价结果已人工确认完成', '客户名称、联系人、收货信息可选补录', '根据场景选择标准版、二维码版或带图版'],
        'readiness_score': 92,
        'must_have_fields': ['订单号', '客户名称', '收货信息', '商品名称', '数量'],
        'optional_fields': ['联系人', '联系电话', '订单备注', '规格', '单位', '金额汇总'],
        'enhancement_fields': ['支付二维码', '商品图片', '订单二维码'],
        'validation_focus': ['订单头字段是否完整', '商品明细行是否集中', '二维码 / 图片版是否按模板版本启用'],
        'next_step': '已接入真实导出，可继续补充更完整的订单头信息录入。'
    },
    {
        'key': 'mall_delivery',
        'label': '发货单',
        'description': '保留品牌、规格、数量等字段，直接衔接发货流程。',
        'status': 'ready',
        'scenario': '适合订单确认后的仓配发货场景，强调数量、规格和收货信息一致。',
        'inherited_fields': ['品牌', '商品名称', '规格', '数量', '备注'],
        'prerequisites': ['订单号', '收货地址', '物流信息'],
        'readiness_note': '当前可生成标准版和带图版发货单；物流字段不足时会保留清晰占位。',
        'rollout_order': 2,
        'value_summary': '适合作为第二阶段，因为依赖订单与物流信息，通常需要先有订货确认再进入发货流转。',
        'template_variants': ['商城发货单（标准版）', '商城发货单（带图版）'],
        'field_focus': ['物流公司与单号', '仓库 / 出库状态', '收货信息', '出库数量与金额', '商品图片'],
        'landing_checklist': ['确认前序订货 / 订单信息已生成', '物流公司、单号、发货时间等字段可选补录', '如需仓配核对，可直接选择带图版模板'],
        'readiness_score': 88,
        'must_have_fields': ['发货单号', '物流公司', '物流单号', '收货信息', '出库数量'],
        'optional_fields': ['仓库', '发货时间', '商品规格', '金额合计', '备注'],
        'enhancement_fields': ['商品图片', '出库状态', '签收 / 配送扩展字段'],
        'validation_focus': ['物流字段是否齐全', '发货数量与商品明细是否对齐', '带图模板是否包含图片字段'],
        'next_step': '已接入真实导出，后续可继续把物流和状态字段做成最小补录入口。'
    },
    {
        'key': 'mall_purchase',
        'label': '采购单',
        'description': '面向供应链下单场景，支持采购单和供应商订单导出。',
        'status': 'ready',
        'scenario': '适合把报价确认结果继续流转给供应商或采购同事执行下单。',
        'inherited_fields': ['品牌', '商品名称', '规格', '数量', '供应商备注'],
        'prerequisites': ['供应商信息', '采购价', '交期'],
        'readiness_note': '当前已接入采购单、供应商订单等真实模板，成本口径可直接用于采购侧导出。',
        'rollout_order': 3,
        'value_summary': '承接报价结果的同时补足供应商与成本字段，可以直接用于供应链沟通。',
        'template_variants': ['商城采购单（标准版）', '商城供应商订单'],
        'field_focus': ['供应商信息', '采购单价', '交期', '数量合计', '商品图片 / 备注'],
        'landing_checklist': ['确认可拿到供应商、采购价、交期等字段', '区分内部采购单与供应商协同单输出口径', '确认数量 / 单位 / 金额字段使用采购侧字典'],
        'readiness_score': 86,
        'must_have_fields': ['采购单号', '供应商名称', '采购价', '数量', '交期'],
        'optional_fields': ['联系人', '联系电话', '规格', '单位', '金额合计', '仓库'],
        'enhancement_fields': ['商品图片', '采购状态', '预计到货时间'],
        'validation_focus': ['供应商字段是否完整', '采购价与数量是否齐全', '交期和采购侧扩展字段是否按模板版本启用'],
        'next_step': '已接入真实导出，后续可继续把供应商通讯信息和仓库字段独立补录。'
    }
]


EXPORT_TEMPLATE_REGISTRY = [
    _make_export_template(
        key='standard_default',
        export_format='standard',
        label='标准报价单（默认）',
        description='适合直接发给客户，包含商品名称、数量、单价和总价。',
        supports_price_types=['market', 'adjusted'],
        default=True,
        source='system',
        use_cases=['客户报价', '标准导出', '常规发送'],
        preview_fields=['商品名称', '规格型号', '数量', '单价', '金额'],
        extension_targets=['客户正式报价', '报价归档']
    ),
    _make_export_template(
        key='internal_default',
        export_format='internal',
        label='内部报价单（利润版）',
        description='包含成本价、利润和利润率，仅供内部核价和审批使用。',
        supports_price_types=['market', 'adjusted', 'cost'],
        default=True,
        source='system',
        use_cases=['内部核价', '利润审批', '成本测算'],
        preview_fields=['商品名称', '市场价', '成本价', '利润额', '利润率'],
        extension_targets=['内部审核流', '成本复盘']
    ),
    _make_export_template(
        key='statement_default',
        export_format='statement',
        label='对账单（简洁版）',
        description='字段简洁，适合和供应商或客户做金额核对。',
        supports_price_types=['market', 'adjusted'],
        default=True,
        source='system',
        use_cases=['供应商对账', '客户核对', '金额确认'],
        preview_fields=['商品名称', '数量', '单价', '金额', '供应商'],
        extension_targets=['月度对账', '结算确认']
    ),
    _make_export_template(
        key='mall_quote_classic',
        export_format='mall_quote',
        label='商城报价单（经典）',
        description='按商城模板字段结构输出，适合继续衔接订单、发货、采购等单据。',
        supports_price_types=['market', 'adjusted'],
        default=True,
        source='mall',
        use_cases=['商城风格报价', '模板延展', '单据衔接'],
        preview_fields=['品牌', '商品名称', '规格', '数量', '备注'],
        extension_targets=['订货单', '发货单', '采购单'],
        doc_type='quote',
        template_variant='classic',
        requires_extra_fields=[],
        mall_template_capability=MALL_TEMPLATE_CAPABILITY,
        mall_extension_hooks=MALL_EXTENSION_HOOKS
    ),
    _make_export_template(
        key='mall_order_standard',
        export_format='mall_quote',
        label='商城订货单（标准版）',
        description='把已确认报价直接整理成正式订货单，适合客户下单确认。',
        supports_price_types=['market', 'adjusted'],
        source='mall',
        use_cases=['客户下单', '成交确认', '订单流转'],
        preview_fields=['订单号', '客户名称', '收货信息', '商品名称', '数量', '金额'],
        extension_targets=['发货单', '合并出库单'],
        doc_type='order',
        template_variant='standard',
        requires_extra_fields=['客户名称', '收货信息']
    ),
    _make_export_template(
        key='mall_order_qrcode',
        export_format='mall_quote',
        label='商城订货单（二维码版）',
        description='订货单页头额外保留支付二维码占位说明，适合商城付款流程。',
        supports_price_types=['market', 'adjusted'],
        source='mall',
        use_cases=['客户下单', '支付引导', '订单确认'],
        preview_fields=['订单号', '客户名称', '商品名称', '数量', '金额', '支付二维码'],
        extension_targets=['发货单'],
        doc_type='order',
        template_variant='qrcode',
        requires_extra_fields=['客户名称', '收货信息', '支付二维码']
    ),
    _make_export_template(
        key='mall_order_with_images',
        export_format='mall_quote',
        label='商城订货单（带图版）',
        description='在订货单明细中输出商品图片字段，适合客户确认商品外观。',
        supports_price_types=['market', 'adjusted'],
        source='mall',
        use_cases=['图文订货', '商品确认', '外观核对'],
        preview_fields=['订单号', '客户名称', '商品图片', '商品名称', '数量', '金额'],
        extension_targets=['发货单（带图版）'],
        doc_type='order',
        template_variant='with_images',
        requires_extra_fields=['客户名称', '收货信息']
    ),
    _make_export_template(
        key='mall_delivery_standard',
        export_format='mall_quote',
        label='商城发货单（标准版）',
        description='按发货流转组织物流与收货字段，适合仓配出库。',
        supports_price_types=['market', 'adjusted'],
        source='mall',
        use_cases=['发货通知', '仓配出库', '收货核对'],
        preview_fields=['发货单号', '物流公司', '物流单号', '收货信息', '商品名称', '出库数量'],
        extension_targets=['入库单', '签收回传'],
        doc_type='delivery',
        template_variant='standard',
        requires_extra_fields=['物流公司', '物流单号', '收货信息']
    ),
    _make_export_template(
        key='mall_delivery_with_images',
        export_format='mall_quote',
        label='商城发货单（带图版）',
        description='在发货单中额外输出商品图片字段，适合仓配核对与签收前确认。',
        supports_price_types=['market', 'adjusted'],
        source='mall',
        use_cases=['图文发货', '仓配核对', '签收确认'],
        preview_fields=['发货单号', '物流信息', '商品图片', '商品名称', '出库数量'],
        extension_targets=['签收回传'],
        doc_type='delivery',
        template_variant='with_images',
        requires_extra_fields=['物流公司', '物流单号', '收货信息']
    ),
    _make_export_template(
        key='mall_purchase_standard',
        export_format='mall_quote',
        label='商城采购单（标准版）',
        description='把匹配结果转换成采购口径单据，优先使用成本价或采购价。',
        supports_price_types=['market', 'adjusted', 'cost'],
        source='mall',
        use_cases=['采购下单', '成本测算', '供应链执行'],
        preview_fields=['采购单号', '供应商', '采购单价', '数量', '交期'],
        extension_targets=['供应商订单', '入库单'],
        doc_type='purchase',
        template_variant='standard',
        requires_extra_fields=['供应商', '交期']
    ),
    _make_export_template(
        key='mall_supplier_order',
        export_format='mall_quote',
        label='商城供应商订单',
        description='面向外部供应商协同的采购订单版本，突出供应商与交付信息。',
        supports_price_types=['market', 'adjusted', 'cost'],
        source='mall',
        use_cases=['供应商协同', '外发下单', '采购执行'],
        preview_fields=['供应商订单号', '供应商', '联系人', '商品名称', '数量', '交期'],
        extension_targets=['入库单'],
        doc_type='supplier_order',
        template_variant='standard',
        requires_extra_fields=['供应商', '联系人', '交期']
    ),
    _make_export_template(
        key='mall_return',
        export_format='mall_quote',
        label='商城退货单',
        description='面向销售退货场景，输出退货数量、原因与关联单号。',
        supports_price_types=['market', 'adjusted'],
        source='mall',
        use_cases=['销售退货', '逆向流转', '售后处理'],
        preview_fields=['退货单号', '关联订单号', '退货原因', '商品名称', '退货数量'],
        extension_targets=['入库单'],
        doc_type='return',
        template_variant='standard',
        requires_extra_fields=['关联订单号', '退货原因']
    ),
    _make_export_template(
        key='mall_purchase_return',
        export_format='mall_quote',
        label='商城采购退货单',
        description='面向供应商退货场景，突出供应商、采购价和退货原因。',
        supports_price_types=['market', 'adjusted', 'cost'],
        source='mall',
        use_cases=['采购退货', '供应商逆向单据', '成本回退'],
        preview_fields=['采购退货单号', '供应商', '采购价', '退货原因', '数量'],
        extension_targets=['供应商对账'],
        doc_type='purchase_return',
        template_variant='standard',
        requires_extra_fields=['供应商', '关联采购单号', '退货原因']
    ),
    _make_export_template(
        key='mall_inbound',
        export_format='mall_quote',
        label='商城入库单',
        description='按仓储入库场景输出仓库、入库时间与商品明细。',
        supports_price_types=['market', 'adjusted', 'cost'],
        source='mall',
        use_cases=['仓储入库', '收货登记', '库存流转'],
        preview_fields=['入库单号', '仓库', '入库时间', '商品名称', '入库数量'],
        extension_targets=['库存台账'],
        doc_type='inbound',
        template_variant='standard',
        requires_extra_fields=['仓库', '入库时间']
    ),
    _make_export_template(
        key='mall_inbound_with_images',
        export_format='mall_quote',
        label='商城入库单（带图版）',
        description='入库单中同时输出商品图片字段，方便收货和仓库核对。',
        supports_price_types=['market', 'adjusted', 'cost'],
        source='mall',
        use_cases=['图文入库', '收货核对', '仓库验货'],
        preview_fields=['入库单号', '仓库', '商品图片', '商品名称', '入库数量'],
        extension_targets=['库存台账'],
        doc_type='inbound',
        template_variant='with_images',
        requires_extra_fields=['仓库', '入库时间']
    ),
    _make_export_template(
        key='mall_merge_outbound',
        export_format='mall_quote',
        label='商城合并出库单',
        description='将当前匹配结果按合单出库口径汇总，适合批量打印与统一出库。',
        supports_price_types=['market', 'adjusted'],
        source='mall',
        use_cases=['合单出库', '批量打印', '仓配汇总'],
        preview_fields=['合并单号', '来源单据', '商品名称', '数量', '收货信息'],
        extension_targets=['发货单'],
        doc_type='merge_outbound',
        template_variant='standard',
        requires_extra_fields=['来源单据', '收货信息']
    ),
    _make_export_template(
        key='mall_order_items',
        export_format='mall_quote',
        label='商城订单商品明细',
        description='聚焦商品逐行明细，适合单独导出订单商品列表或交给运营整理。',
        supports_price_types=['market', 'adjusted', 'cost'],
        source='mall',
        use_cases=['商品明细导出', '运营整理', '订单行级核对'],
        preview_fields=['订单号', '商品编码', '商品名称', '规格', '数量', '单价'],
        extension_targets=['数据归档'],
        doc_type='order_items',
        template_variant='standard',
        requires_extra_fields=[]
    ),
    _make_export_template(
        key='dropdown_default',
        export_format='dropdown',
        label='待选报价单（客服筛选）',
        description='每个报价项保留候选商品下拉框，便于客服人工补选。',
        supports_price_types=['market'],
        default=True,
        source='system',
        use_cases=['客服补选', '人工确认', '候选比对'],
        preview_fields=['报价项', '候选商品', '下拉选择', '市场价'],
        extension_targets=['人工筛选流程', '客服二次确认']
    )
]




def _get_export_template_registry_payload():
    templates = [dict(template) for template in EXPORT_TEMPLATE_REGISTRY]
    defaults = {}
    for template in templates:
        if template.get('default'):
            defaults[template['export_format']] = template['key']
    return {
        'templates': templates,
        'defaults': defaults
    }



def _get_export_template_definition(template_key='', export_format=''):
    template_key = str(template_key or '').strip()
    export_format = str(export_format or '').strip()
    for template in EXPORT_TEMPLATE_REGISTRY:
        if template_key and template.get('key') != template_key:
            continue
        if export_format and template.get('export_format') != export_format:
            continue
        return dict(template)
    return None



def _get_default_export_template(export_format):
    export_format = str(export_format or '').strip()
    for template in EXPORT_TEMPLATE_REGISTRY:
        if template.get('export_format') == export_format and template.get('default'):
            return dict(template)
    return None


WORKSPACE_PAGE_META = {
    'dashboard': {
        'tab': 'upload',
        'eyebrow': '入口',
        'title': '两步导入',
        'description': '先导入商品库，再导入报价来源。完成后进入报价确认台确认与导出。',
        'pills': ['商品底座', '报价来源', '确认导出'],
        'note': '总览'
    },
    'templates': {
        'tab': 'templates',
        'eyebrow': '模板',
        'title': '模板中心',
        'description': '高频模板放前面，详细字段和扩展能力在模板中心查看。',
        'pills': ['标准报价单', '待选报价单', '商城模板'],
        'note': '模板中心'
    },
    'quotes': {
        'tab': 'match',
        'eyebrow': '报价',
        'title': '报价确认台',
        'description': '直接上传、筛选、确认和导出。',
        'pills': ['上传报价单', '人工确认', '导出'],
        'note': '报价确认台'
    },
    'catalog': {
        'tab': 'catalog',
        'eyebrow': '商品',
        'title': '商品库',
        'description': '直接筛选、直接看卡片、点开看详情。',
        'pills': ['关键词筛选', '图片浏览', '详情核对'],
        'note': '商品库'
    },
    'history': {
        'tab': 'history',
        'eyebrow': '历史',
        'title': '历史记录',
        'description': '查看历史报价与导出记录。',
        'pills': ['查看记录', '快速回看', '继续处理'],
        'note': '历史记录'
    },
    'synonyms': {
        'tab': 'synonyms',
        'eyebrow': '词库',
        'title': '同义词库',
        'description': '维护常用别名、简称和行业叫法。',
        'pills': ['别名维护', '行业叫法', '持续学习'],
        'note': '同义词库'
    },
    'guide': {
        'tab': 'guide',
        'eyebrow': '说明',
        'title': '说明',
        'description': '员工上手、模板选择和常见问题都集中在这里。',
        'pills': ['两步导入', '模板说明', '常见问题'],
        'note': '说明'
    }
}

WORKSPACE_ROUTES = {
    'dashboard': '/',
    'templates': '/templates',
    'quotes': '/quotes',
    'catalog': '/catalog',
    'history': '/history',
    'synonyms': '/synonyms',
    'guide': '/guide'
}


def _build_workspace_context(current_page='dashboard'):
    current_page = str(current_page or 'dashboard').strip() or 'dashboard'
    page_meta = dict(WORKSPACE_PAGE_META.get(current_page, WORKSPACE_PAGE_META['dashboard']))
    initial_tab = page_meta.pop('tab', 'upload')

    products_loaded = products_data is not None
    products_count = len(products_data) if products_data else 0
    synonyms = load_synonyms()
    categories, suppliers, brands = _get_catalog_filter_options()
    export_registry = _get_export_template_registry_payload()

    return {
        'products_loaded': products_loaded,
        'products_count': products_count,
        'products_source': products_data_source,
        'synonyms': synonyms,
        'catalog_categories': categories,
        'catalog_suppliers': suppliers,
        'catalog_brands': brands,
        'export_templates': export_registry['templates'],
        'export_template_defaults': export_registry['defaults'],
        'current_page': current_page,
        'initial_tab': initial_tab,
        'page_meta': page_meta,
        'workspace_routes': WORKSPACE_ROUTES
    }


# =============== 页面路由 ===============

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.svg', mimetype='image/svg+xml')

@app.route('/')
@app.route('/dashboard')
def index():
    """主页"""
    return render_template('index.html', **_build_workspace_context('dashboard'))


@app.route('/templates')
def templates_page():
    """模板中心"""
    return render_template('index.html', **_build_workspace_context('templates'))


@app.route('/quotes')
def quotes_page():
    """报价确认台"""
    return render_template('index.html', **_build_workspace_context('quotes'))


@app.route('/catalog')
def catalog_page():
    """商品库"""
    return render_template('index.html', **_build_workspace_context('catalog'))


@app.route('/guide')
def guide_page():
    """说明"""
    return render_template('index.html', **_build_workspace_context('guide'))


@app.route('/history')
def history_page():
    """历史记录"""
    return render_template('index.html', **_build_workspace_context('history'))


@app.route('/synonyms')
def synonyms_page():
    """同义词管理"""
    return render_template('index.html', **_build_workspace_context('synonyms'))



@app.route('/api/catalog/products', methods=['GET'])
def get_catalog_products():
    """获取商品库浏览列表"""
    keyword = request.args.get('keyword', '', type=str)
    category = request.args.get('category', '', type=str)
    supplier = request.args.get('supplier', '', type=str)
    brand = request.args.get('brand', '', type=str)
    has_image = request.args.get('has_image', '', type=str)
    page = request.args.get('page', default=1, type=int)
    page_size = request.args.get('page_size', default=0, type=int)
    limit = request.args.get('limit', default=0, type=int)

    if page_size <= 0:
        page_size = limit or 24

    if V2_CATALOG_AVAILABLE:
        try:
            return jsonify(_run_async_task(_build_v2_catalog_response_async(
                keyword=keyword,
                category=category,
                supplier=supplier,
                brand=brand,
                has_image=has_image,
                page=page,
                page_size=page_size
            )))
        except Exception:
            pass

    return jsonify(_build_catalog_response(
        keyword=keyword,
        category=category,
        supplier=supplier,
        brand=brand,
        has_image=has_image,
        page=page,
        page_size=page_size
    ))


@app.route('/api/catalog/product/<product_code>', methods=['GET'])
def get_catalog_product_detail(product_code):
    """获取单个商品详情"""
    detail = None
    if V2_CATALOG_AVAILABLE:
        try:
            detail = _run_async_task(_build_v2_catalog_detail_response_async(product_code))
        except Exception:
            detail = None
    if not detail:
        detail = _build_catalog_detail_response(product_code)
    if not detail:
        return jsonify({'success': False, 'message': '商品不存在'})

    return jsonify({
        'success': True,
        'product': detail
    })


@app.route('/api/catalog/search_for_quote', methods=['POST'])
def catalog_search_for_quote():
    """根据报价项搜索商品库，辅助人工审核"""
    data = request.get_json() or {}
    query_item = data.get('query_item') or {}
    keyword = _normalize_text_value(data.get('keyword'))

    if not keyword:
        keyword = _normalize_text_value(query_item.get('name')) or _normalize_text_value(query_item.get('spec')) or _normalize_text_value(query_item.get('remark'))

    if not keyword:
        return jsonify({'success': False, 'message': '缺少搜索关键词'})

    normalized_item = normalize_quote_item({
        'name': query_item.get('name', ''),
        'spec': query_item.get('spec', ''),
        'unit': query_item.get('unit', ''),
        'remark': query_item.get('remark', '')
    })

    search_terms = []
    for value in [
        keyword,
        normalized_item.get('normalized_name', ''),
        normalized_item.get('normalized_spec', ''),
        _normalize_text_value(query_item.get('name')),
        _normalize_text_value(query_item.get('spec'))
    ]:
        value = _normalize_text_value(value)
        if value and value not in search_terms:
            search_terms.append(value)

    candidates = []
    if V2_CATALOG_AVAILABLE:
        try:
            candidates = _run_async_task(_search_v2_catalog_for_quote_async(keyword, search_terms, normalized_item, limit=20))
        except Exception:
            candidates = []

    if not candidates:
        seen_codes = set()
        for product in products_data or []:
            item = _build_product_catalog_item(product)
            score = _score_catalog_candidate(item, search_terms, normalized_item)

            if score <= 0:
                continue

            code_key = item['code'] or f"__idx_{item['index']}"
            if code_key in seen_codes:
                continue
            seen_codes.add(code_key)

            image_count = len(item['images']) if isinstance(item['images'], list) else 0
            item['image_count'] = image_count
            item['has_image'] = bool(item['image_url'] or item['source_image_url'] or image_count)
            item['catalog_score'] = score
            item['catalog_source'] = 'legacy_json'
            candidates.append(item)

    candidates.sort(key=lambda x: (x.get('catalog_score', 0), x.get('has_image', False), x.get('market_price', 0)), reverse=True)

    return jsonify({
        'success': True,
        'keyword': keyword,
        'items': candidates[:20],
        'total': len(candidates),
        'catalog_source': candidates[0].get('catalog_source') if candidates else ('postgres_v2' if V2_CATALOG_AVAILABLE else 'legacy_json')
    })


# =============== API路由 ===============

@app.route('/api/catalog/search_by_image_for_quote', methods=['POST'])
def catalog_search_by_image_for_quote():
    """按图片为当前报价项召回相似商品"""
    if not V2_IMAGE_SEARCH_AVAILABLE:
        return jsonify({
            'success': False,
            'message': f'图搜图能力不可用：{V2_IMAGE_SEARCH_IMPORT_ERROR or "依赖未安装"}'
        })

    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '请先选择图片'})

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': '请先选择图片'})

    top_k = max(1, min(int(request.form.get('top_k', 12) or 12), 20))
    query_text = _normalize_text_value(request.form.get('query_text')) or ''
    spec_hint = _normalize_text_value(request.form.get('spec_hint')) or ''
    brand_hint = _normalize_text_value(request.form.get('brand_hint')) or ''
    provider = _normalize_text_value(request.form.get('provider')) or ''
    model_name = _normalize_text_value(request.form.get('model_name')) or ''
    file_bytes = file.read()
    if not file_bytes:
        return jsonify({'success': False, 'message': '图片内容为空'})

    try:
        result = _run_async_task(_search_catalog_by_image_async(
            file_bytes,
            top_k=top_k,
            query_text=query_text,
            spec_hint=spec_hint,
            brand_hint=brand_hint,
            provider=provider,
            model_name=model_name,
        ))
        return jsonify({
            'success': True,
            **result
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'图片检索失败：{str(e)}'
        })


@app.route('/api/catalog/image_embedding_status', methods=['GET'])
def get_catalog_image_embedding_status():
    """查询当前图搜图 embedding provider 状态"""
    if not V2_IMAGE_SEARCH_AVAILABLE:
        return jsonify({
            'success': False,
            'message': f'图搜图能力不可用：{V2_IMAGE_SEARCH_IMPORT_ERROR or "依赖未安装"}'
        }), 503
    try:
        return jsonify({
            'success': True,
            **_run_async_task(_get_v2_image_embedding_status_async()),
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'读取图搜图状态失败：{str(e)}'
        }), 500


@app.route('/api/catalog/image_embedding_jobs', methods=['POST'])
def create_catalog_image_embedding_job():
    """从 Flask 工作台提交图片 embedding 后台生成任务"""
    if not V2_IMAGE_SEARCH_AVAILABLE:
        return jsonify({
            'success': False,
            'message': f'图搜图能力不可用：{V2_IMAGE_SEARCH_IMPORT_ERROR or "依赖未安装"}'
        }), 503

    payload = request.get_json(silent=True) or {}
    provider = _normalize_text_value(payload.get('provider')) or V2_CLIP_EMBEDDING_PROVIDER
    model_name = _normalize_text_value(payload.get('model_name')) or ''
    provider, model_name = _normalize_image_search_provider(provider, model_name)

    allowed_providers = {V2_IMAGE_EMBEDDING_PROVIDER, V2_CLIP_EMBEDDING_PROVIDER}
    if provider not in allowed_providers:
        return jsonify({
            'success': False,
            'message': f'暂不支持的 embedding provider：{provider}'
        }), 400

    limit = _safe_int(payload.get('limit'), default=20, min_value=1, max_value=1000)
    commit_every = _safe_int(payload.get('commit_every'), default=5, min_value=1, max_value=limit)
    only_missing = True if payload.get('only_missing') is None else _is_truthy_form_value(payload.get('only_missing'))
    dry_run = _is_truthy_form_value(payload.get('dry_run'))

    try:
        task = V2GenerateImageEmbeddingsTask.delay(
            provider=provider,
            model_name=model_name,
            limit=limit,
            only_missing=only_missing,
            commit_every=commit_every,
            dry_run=dry_run,
        )
        return jsonify({
            'success': True,
            'task_id': task.id,
            'status': 'queued',
            'provider': provider,
            'model_name': model_name,
            'limit': limit,
            'commit_every': commit_every,
            'only_missing': only_missing,
            'dry_run': dry_run,
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'提交 embedding 任务失败：{str(e)}'
        }), 503


@app.route('/api/catalog/image_embedding_jobs/<task_id>', methods=['GET'])
def get_catalog_image_embedding_job(task_id):
    """查询 Flask 工作台提交的图片 embedding 后台任务状态"""
    if not V2_IMAGE_SEARCH_AVAILABLE:
        return jsonify({
            'success': False,
            'message': f'图搜图能力不可用：{V2_IMAGE_SEARCH_IMPORT_ERROR or "依赖未安装"}'
        }), 503

    task_id = _normalize_text_value(task_id)
    if not task_id:
        return jsonify({'success': False, 'message': '任务 ID 不能为空'}), 400

    try:
        result = V2CeleryApp.AsyncResult(task_id)
        response = {
            'success': True,
            'task_id': task_id,
            'status': result.status,
            'ready': result.ready(),
        }
        if result.ready():
            if result.successful():
                response['result'] = result.result
            else:
                response['error'] = str(result.result)
        return jsonify(response)
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'读取 embedding 任务失败：{str(e)}'
        }), 500


@app.route('/api/catalog/image_asset/<int:asset_id>/file', methods=['GET'])
def get_catalog_image_asset_file(asset_id):
    """返回 V2 归档后的商品图片文件"""
    if not V2_IMAGE_SEARCH_AVAILABLE:
        return jsonify({
            'success': False,
            'message': f'图搜图能力不可用：{V2_IMAGE_SEARCH_IMPORT_ERROR or "依赖未安装"}'
        }), 503

    try:
        async def _load_asset():
            async with V2AsyncSessionLocal() as session:
                return await session.scalar(sa_select(V2ImageAsset).where(V2ImageAsset.id == asset_id))

        asset = _run_async_task(_load_asset())
        if asset is None:
            return jsonify({'success': False, 'message': '图片资产不存在'}), 404

        file_path = v2_resolve_archive_file_path(asset.storage_key)
        if file_path is None:
            return jsonify({'success': False, 'message': '归档图片不存在'}), 404

        return send_file(
            file_path,
            mimetype=asset.mime_type or 'application/octet-stream',
            download_name=file_path.name
        )
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'读取归档图片失败：{str(e)}'
        }), 500


@app.route('/api/catalog/sync_v2_status', methods=['GET'])
def get_catalog_sync_v2_status():
    """查询 PostgreSQL 商品同步状态"""
    try:
        return jsonify(_run_async_task(_get_v2_catalog_sync_status_async()))
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'读取同步状态失败：{str(e)}'
        }), 500


@app.route('/api/catalog/sync_v2_manual', methods=['POST'])
def run_catalog_sync_v2_manual():
    """手动把当前商品库文件同步到 V2 PostgreSQL"""
    requested_by = _normalize_text_value((request.get_json(silent=True) or {}).get('requested_by')) or 'flask-workbench'
    try:
        result = _run_async_task(_run_v2_catalog_manual_sync_async(requested_by=requested_by))
        load_products()
        stats = result.get('stats', {}) or {}
        diff_summary = stats.get('diff_summary', {}) or {}
        created_rows = diff_summary.get('created_rows')
        updated_rows = diff_summary.get('updated_rows')
        unchanged_rows = diff_summary.get('unchanged_rows')
        stale_images = diff_summary.get('stale_images_detected') or 0
        failed_rows = diff_summary.get('failed_rows') or 0
        retried_rows = diff_summary.get('retried_rows') or 0
        if created_rows is not None and updated_rows is not None and unchanged_rows is not None:
            message = f'V2 商品同步完成：新增 {created_rows}，更新 {updated_rows}，无变化 {unchanged_rows}'
            if failed_rows:
                message += f'，失败 {failed_rows}'
            if retried_rows:
                message += f'，重试 {retried_rows}'
            if stale_images:
                message += f'，旧图待处理 {stale_images}'
            message += '。'
        else:
            message = f"V2 商品同步完成，处理 {stats.get('processed', 0)} 条。"
        return jsonify({
            'success': True,
            'message': message,
            'products_source': products_data_source,
            **result,
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'同步失败：{str(e)}'
        }), 500


@app.route('/api/catalog/sync_from_mall', methods=['POST'])
def run_catalog_sync_from_mall():
    """使用 Playwright 从商城页面抓取商品并同步到 V2 PostgreSQL"""
    payload = request.get_json(silent=True) or {}
    requested_by = _normalize_text_value(payload.get('requested_by')) or 'flask-mall-scrape'
    dry_run = _is_truthy_form_value(payload.get('dry_run'))
    try:
        result = _run_async_task(_run_v2_catalog_mall_scrape_sync_async(requested_by=requested_by, options=payload, dry_run=dry_run))
        if not dry_run:
            load_products()
        stats = result.get('stats', {}) or {}
        diff_summary = stats.get('diff_summary', {}) or {}
        scrape_stats = (result.get('scrape') or {}).get('stats') or {}
        extracted = scrape_stats.get('extracted_items', 0)
        pages = scrape_stats.get('pages_visited', 0)
        created_rows = diff_summary.get('created_rows', 0)
        updated_rows = diff_summary.get('updated_rows', 0)
        unchanged_rows = diff_summary.get('unchanged_rows', 0)
        failed_rows = diff_summary.get('failed_rows', 0)
        prefix = '商城抓取预检完成' if dry_run else '商城抓取完成'
        message = (
            f'{prefix}：页面 {pages}，提取 {extracted}，'
            f'新增 {created_rows}，更新 {updated_rows}，无变化 {unchanged_rows}'
        )
        if failed_rows:
            message += f'，失败 {failed_rows}'
        message += '。'
        return jsonify({
            'success': True,
            'message': message,
            'products_source': products_data_source,
            **result,
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'商城抓取同步失败：{str(e)}'
        }), 500


@app.route('/api/catalog/mall_sync_jobs', methods=['POST'])
def create_catalog_mall_sync_job():
    """提交商城抓取同步后台任务"""
    if not V2_CATALOG_AVAILABLE:
        return jsonify({
            'success': False,
            'message': f'V2 商品同步不可用：{V2_CATALOG_IMPORT_ERROR or "依赖未安装"}'
        }), 503

    payload = request.get_json(silent=True) or {}
    requested_by = _normalize_text_value(payload.get('requested_by')) or 'catalog-page-mall-scrape'
    dry_run = _is_truthy_form_value(payload.get('dry_run'))
    options = v2_pick_mall_scrape_options(payload)

    try:
        task = V2ScrapeMallSyncTask.delay(
            requested_by=requested_by,
            options=options,
            dry_run=dry_run,
        )
        return jsonify({
            'success': True,
            'task_id': task.id,
            'status': 'queued',
            'dry_run': dry_run,
            'options': {
                key: value
                for key, value in options.items()
                if key not in {'storage_state_path'}
            },
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'提交商城抓取任务失败：{str(e)}'
        }), 503


@app.route('/api/catalog/mall_sync_jobs/<task_id>', methods=['GET'])
def get_catalog_mall_sync_job(task_id):
    """查询商城抓取同步后台任务状态"""
    if not V2_CATALOG_AVAILABLE:
        return jsonify({
            'success': False,
            'message': f'V2 商品同步不可用：{V2_CATALOG_IMPORT_ERROR or "依赖未安装"}'
        }), 503

    task_id = _normalize_text_value(task_id)
    if not task_id:
        return jsonify({'success': False, 'message': '任务 ID 不能为空'}), 400

    try:
        result = V2CeleryApp.AsyncResult(task_id)
        response = {
            'success': True,
            'task_id': task_id,
            'status': result.status,
            'ready': result.ready(),
        }
        if result.ready():
            if result.successful():
                task_result = result.result or {}
                response['result'] = task_result
                if not task_result.get('dry_run'):
                    load_products()
                    response['products_source'] = products_data_source
                    response['products_count'] = len(products_data or [])
            else:
                response['error'] = str(result.result)
        return jsonify(response)
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'读取商城抓取任务失败：{str(e)}'
        }), 500


@app.route('/api/catalog/scrape_mall_preview', methods=['POST'])
def preview_catalog_sync_from_mall():
    """只预检 Playwright 商城抓取与同步差异，不写入数据库"""
    payload = request.get_json(silent=True) or {}
    requested_by = _normalize_text_value(payload.get('requested_by')) or 'flask-mall-scrape-preview'
    try:
        result = _run_async_task(_run_v2_catalog_mall_scrape_sync_async(requested_by=requested_by, options=payload, dry_run=True))
        stats = result.get('stats', {}) or {}
        diff_summary = stats.get('diff_summary', {}) or {}
        scrape_stats = (result.get('scrape') or {}).get('stats') or {}
        extracted = scrape_stats.get('extracted_items', 0)
        pages = scrape_stats.get('pages_visited', 0)
        message = (
            f"商城抓取预检完成：页面 {pages}，提取 {extracted}，"
            f"预计新增 {diff_summary.get('created_rows', 0)}，"
            f"预计更新 {diff_summary.get('updated_rows', 0)}，"
            f"预计无变化 {diff_summary.get('unchanged_rows', 0)}。"
        )
        return jsonify({
            'success': True,
            'message': message,
            'products_source': products_data_source,
            **result,
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'商城抓取预检失败：{str(e)}'
        }), 500


@app.route('/api/upload_products', methods=['POST'])
def upload_products():
    """上传商品库"""
    global products_data, products_data_source, matcher

    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '没有选择文件'})

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': '没有选择文件'})

    if file and allowed_file(file.filename):
        try:
            sync_to_v2 = _is_truthy_form_value(request.form.get('sync_to_v2'))
            requested_by = _normalize_text_value(request.form.get('requested_by')) or 'flask-upload-products'

            if file.filename.lower().endswith('.csv'):
                df = pd.read_csv(file, encoding='utf-8-sig')
            else:
                df = pd.read_excel(file, engine='xlrd' if file.filename.endswith('.xls') else 'openpyxl')

            def safe_value(val, default=''):
                if pd.isna(val) or val is None:
                    return default
                if isinstance(val, float) and val != val:
                    return default
                return val

            products = []
            for _, row in df.iterrows():
                product = {
                    'code': safe_value(row.get('* 商品编码', '')),
                    'name': safe_value(row.get('* 商品名称', '')),
                    'model': safe_value(row.get('* 型号', '')),
                    'category': safe_value(row.get('* 商品类别', '')),
                    'unit': safe_value(row.get('* 单位', '')),
                    'market_price': safe_value(row.get('* 市场价', 0), 0),
                    'cost_price': _pick_cost_price(row),
                    'brand': safe_value(row.get('商品品牌', '')),
                    'supplier': safe_value(row.get('所属供应商', '')),
                    'status': safe_value(row.get('状态', '')),
                    'intro': safe_value(row.get('商品介绍', '')),
                }
                if product['name'] and str(product['name']).strip():
                    products.append(product)

            products_file = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], 'products.json')
            last_uploaded_file = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], 'products.last_uploaded.json')
            os.makedirs(os.path.dirname(products_file), exist_ok=True)
            with open(products_file, 'w', encoding='utf-8') as f:
                json.dump(products, f, ensure_ascii=False, indent=2)
            with open(last_uploaded_file, 'w', encoding='utf-8') as f:
                json.dump(products, f, ensure_ascii=False, indent=2)

            products = [_annotate_product_cost_fields(product, source='uploaded') for product in products]

            prepared_products = _prepare_products_for_runtime(products, source='uploaded')
            _set_runtime_products_snapshot(prepared_products, source='uploaded_excel')

            sync_result = None
            sync_warning = ''
            if sync_to_v2:
                if V2_CATALOG_AVAILABLE:
                    try:
                        sync_result = _run_async_task(_run_v2_catalog_items_sync_async(
                            products,
                            requested_by=requested_by,
                            source_name='products_upload_inline',
                        ))
                        load_products()
                    except Exception as exc:
                        sync_warning = str(exc)
                else:
                    sync_warning = V2_CATALOG_IMPORT_ERROR or 'V2 商品同步当前不可用'

            message = f'成功导入 {len(products)} 个商品'
            if sync_to_v2 and sync_result:
                message = f'成功导入 {len(products)} 个商品，并已同步到 V2'
            elif sync_to_v2 and sync_warning:
                message = f'已导入 {len(products)} 个商品，但同步到 V2 失败：{sync_warning}'

            return jsonify({
                'success': True,
                'message': message,
                'count': len(products),
                'products_source': products_data_source,
                'sync_v2_requested': sync_to_v2,
                'sync_v2_success': bool(sync_result),
                'sync_v2_warning': sync_warning,
                'sync_job': (sync_result or {}).get('job') if sync_result else None,
            })

        except Exception as e:
            return jsonify({'success': False, 'message': f'导入失败: {str(e)}'})

    return jsonify({'success': False, 'message': '不支持的文件格式'})


@app.route('/api/upload_quote', methods=['POST'])
def upload_quote():
    """上传报价单"""
    global quote_items, match_results

    print("=== 收到报价单上传请求 ===")

    if matcher is None:
        # 尝试加载商品库
        if not load_products():
            return jsonify({'success': False, 'message': '请先导入商品库！请先在左侧上传商品库Excel文件'})

    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '没有选择文件'})

    file = request.files['file']
    print(f"上传文件名: {file.filename}")

    if file.filename == '':
        return jsonify({'success': False, 'message': '没有选择文件'})

    if file and allowed_file(file.filename):
        try:
            # 解析报价单
            print("开始解析报价单...")
            handler = ExcelHandler()
            quote_items = handler.parse_quote(file)

            if not quote_items:
                return jsonify({'success': False, 'message': '报价单解析失败！未能识别任何报价项，请检查Excel格式是否正确'})

            quote_items = [normalize_quote_item(item) for item in quote_items]

            # 执行匹配
            print(f"开始匹配 {len(quote_items)} 个报价项...")
            synonyms = load_synonyms()
            current_match_context['source_type'] = 'excel'
            current_match_context['template_name'] = ''
            current_match_context['template_hit'] = False
            match_results = match_quote_items(quote_items, synonyms, use_ai=False)

            print(f"匹配完成，共 {len(match_results)} 个结果")

            return jsonify({
                'success': True,
                'message': f'成功解析 {len(quote_items)} 个报价项，已完成商品匹配',
                'products_source': products_data_source,
                'quote_items': quote_items,
                'match_results': match_results
            })

        except Exception as e:
            import traceback
            print("=== 报价单解析错误 ===")
            traceback.print_exc()
            print("=====================")
            return jsonify({'success': False, 'message': f'解析失败: {str(e)}'})

    return jsonify({'success': False, 'message': '不支持的文件格式，请上传 .xls 或 .xlsx 文件'})


@app.route('/api/smart_parse', methods=['POST'])
def smart_parse():
    """智能解析报价单 - 自动识别列含义"""
    global smart_parser, parse_result_cache, quote_items

    print("=== 收到智能解析请求 ===")

    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '没有选择文件'})

    file = request.files['file']
    print(f"上传文件名: {file.filename}")

    if file.filename == '':
        return jsonify({'success': False, 'message': '没有选择文件'})

    if file and allowed_file(file.filename):
        try:
            # 加载已保存的模板
            templates_data = load_templates()
            templates = templates_data.get('templates', [])
            print(f"已加载 {len(templates)} 个解析模板")

            # 使用智能解析器
            smart_parser = SmartQuoteParser()
            parse_result = smart_parser.parse(file, templates)

            # 缓存解析结果
            parse_result_cache = parse_result

            print(f"解析完成: {len(parse_result.get('column_mapping', {}))} 列")
            print(f"数据起始行: {parse_result.get('data_start_row', 0)}")

            # 如果匹配到模板，添加提示
            if parse_result.get('matched_template'):
                print(f"自动匹配模板: {parse_result['matched_template'].get('name')}")

            return jsonify({
                'success': True,
                'parse_result': parse_result
            })

        except Exception as e:
            import traceback
            print("=== 智能解析错误 ===")
            traceback.print_exc()
            print("=====================")
            return jsonify({'success': False, 'message': f'解析失败: {str(e)}'})

    return jsonify({'success': False, 'message': '不支持的文件格式'})


@app.route('/api/confirm_mapping', methods=['POST'])
def confirm_mapping():
    """确认列映射并提取报价项"""
    global smart_parser, parse_result_cache, quote_items, match_results, current_match_context

    if parse_result_cache is None:
        return jsonify({'success': False, 'message': '请先上传报价单'})

    data = request.get_json() or {}
    confirmed_mapping = data.get('column_mapping') or {}

    print(f"=== 收到列映射确认 ===")
    print(f"用户确认映射: {confirmed_mapping}")

    try:
        mapping_dict = {int(col_idx_str): col_type for col_idx_str, col_type in confirmed_mapping.items()}
        source = parse_result_cache.get('source', 'excel')
        matched_template = parse_result_cache.get('matched_template') or {}
        matched_template_name = matched_template.get('name', '')
        template_hit = bool(matched_template_name)

        if source == 'ocr':
            ocr_rows = parse_result_cache.get('ocr_rows', [])
            quote_items = get_ocr_parsed_items(ocr_rows, mapping_dict)
        else:
            if smart_parser is None:
                return jsonify({'success': False, 'message': '请先上传报价单'})
            smart_parser.apply_learned_mapping(mapping_dict)
            quote_items = smart_parser.get_parsed_items(mapping_dict)

        mapping_changed = False
        mapping_signature = ''
        if source in {'excel', 'ocr'}:
            parse_result_cache, updated_template = _upsert_learned_template(parse_result_cache, mapping_dict, source_type=source)
            matched_template_name = (updated_template or {}).get('name', '')
            template_hit = bool(matched_template_name)
            mapping_changed = bool((updated_template or {}).get('last_mapping_changed'))
            mapping_signature = (updated_template or {}).get('mapping_signature', '')

        quote_items = _enrich_quote_items(quote_items, source, mapping_changed=mapping_changed, mapping_signature=mapping_signature)
        if not quote_items:
            return jsonify({'success': False, 'message': '未能提取到有效的报价项'})

        print(f"开始匹配 {len(quote_items)} 个报价项...")
        match_results = _rebuild_match_results(
            quote_items,
            source,
            matched_template_name,
            template_hit,
            mapping_changed=mapping_changed,
            mapping_signature=mapping_signature
        )
        print(f"匹配完成，共 {len(match_results)} 个结果")

        return jsonify({
            'success': True,
            'message': f'成功解析 {len(quote_items)} 个报价项',
            'products_source': products_data_source,
            'quote_items': quote_items,
            'match_results': match_results
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'处理失败: {str(e)}'})


@app.route('/api/get_match_results', methods=['GET'])
def get_match_results():
    """获取匹配结果"""
    return jsonify({
        'success': True,
        'products_source': products_data_source,
        'quote_items': quote_items,
        'match_results': match_results
    })


@app.route('/api/confirm_selection', methods=['POST'])
def confirm_selection():
    """确认选择"""
    global current_match_context

    data = request.get_json() or {}
    item_index = data.get('item_index')
    selected_product = data.get('selected_product')
    action = data.get('action')

    if item_index is None or item_index >= len(match_results):
        return jsonify({'success': False, 'message': '无效的索引'})

    result_row = match_results[item_index]
    result_row['confirmed'] = True
    result_row['action'] = action
    result_row['selected_product'] = selected_product if action == 'select' and selected_product else None

    try:
        _save_match_feedback(item_index, result_row, selected_product, action)
        _relearn_after_confirmation(item_index)
    except Exception as e:
        import traceback
        print(f'保存匹配反馈失败: {e}')
        traceback.print_exc()

    return jsonify({'success': True})


@app.route('/api/export_templates', methods=['GET'])
def get_export_templates():
    """获取导出模板注册表"""
    payload = _get_export_template_registry_payload()
    return jsonify({
        'success': True,
        'templates': payload['templates'],
        'defaults': payload['defaults']
    })


@app.route('/api/export_quote', methods=['POST'])
def export_quote():
    """导出报价单"""
    try:
        data = request.get_json()
        results = data.get('results', [])
        price_adjustment = data.get('price_adjustment')
        export_format = data.get('export_format', 'standard')
        price_type = data.get('price_type', 'market')
        customer_name = data.get('customer_name', '')
        export_template_key = data.get('export_template_key', '')

        template_definition = None
        if export_template_key:
            template_definition = _get_export_template_definition(template_key=export_template_key)
            if not template_definition:
                return jsonify({'success': False, 'message': '所选导出模板不存在'})
            export_format = template_definition.get('export_format', export_format)
        else:
            template_definition = _get_default_export_template(export_format)

        supported_price_types = template_definition.get('supports_price_types', []) if template_definition else []
        if supported_price_types and price_type not in supported_price_types:
            return jsonify({'success': False, 'message': '当前导出模板不支持所选价格类型'})

        # 生成Excel
        handler = ExcelHandler()
        output_path = handler.export_quote(
            results, app.config['OUTPUT_FOLDER'],
            price_adjustment=price_adjustment,
            export_format=export_format,
            price_type=price_type,
            customer_name=customer_name,
            template_definition=template_definition
        )

        filename = os.path.basename(output_path)
        return jsonify({
            'success': True,
            'message': '导出成功',
            'filename': filename,
            'download_url': f'/download/{filename}',
            'export_format': export_format,
            'export_template_key': template_definition.get('key') if template_definition else export_template_key
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'导出失败: {str(e)}'})


@app.route('/api/export_quote_dropdown', methods=['POST'])
def export_quote_dropdown():
    """导出带下拉框的报价单（供客服人工选择）"""
    global match_results

    try:
        data = request.get_json()
        customer_name = data.get('customer_name', '')

        # 使用全局的match_results
        if not match_results:
            return jsonify({'success': False, 'message': '没有匹配结果，请先上传报价单'})

        # 生成带下拉框的Excel
        handler = ExcelHandler()
        output_path = handler.export_quote_with_dropdown(
            match_results,
            app.config['OUTPUT_FOLDER'],
            customer_name=customer_name
        )

        filename = os.path.basename(output_path)
        return jsonify({
            'success': True,
            'message': '导出成功',
            'filename': filename,
            'download_url': f'/download/{filename}'
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'导出失败: {str(e)}'})


@app.route('/download/<filename>')
def download_file(filename):
    """下载文件"""
    return send_from_directory(app.config['OUTPUT_FOLDER'], filename, as_attachment=True)


@app.route('/api/get_supplier_variants', methods=['POST'])
def get_supplier_variants():
    """获取同一产品不同供应商价格对比"""
    if matcher is None:
        if not load_products():
            return jsonify({'success': False, 'message': '请先导入商品库'})

    data = request.get_json()
    product_name = data.get('product_name', '')

    if not product_name:
        return jsonify({'success': False, 'message': '请提供产品名称'})

    variants = matcher.find_supplier_variants(product_name)

    return jsonify({
        'success': True,
        'product_name': product_name,
        'variants': variants,
        'count': len(variants)
    })


# =============== 同义词管理 ===============

@app.route('/api/get_synonyms', methods=['GET'])
def get_synonyms():
    """获取同义词库"""
    synonyms = load_synonyms()
    return jsonify({
        'success': True,
        'synonyms': synonyms
    })


@app.route('/api/add_synonym', methods=['POST'])
def add_synonym():
    """添加同义词"""
    data = request.get_json()
    word = data.get('word', '').strip()
    synonyms_list = data.get('synonyms', [])

    if not word:
        return jsonify({'success': False, 'message': '主词不能为空'})

    synonyms = load_synonyms()
    synonyms[word] = synonyms_list
    save_synonyms(synonyms)

    # 更新匹配器的同义词
    if matcher:
        matcher.update_synonyms(synonyms)

    return jsonify({'success': True, 'message': '添加成功'})


@app.route('/api/update_synonym', methods=['POST'])
def update_synonym():
    """更新同义词"""
    data = request.get_json()
    word = data.get('word', '').strip()
    synonyms_list = data.get('synonyms', [])

    if not word:
        return jsonify({'success': False, 'message': '主词不能为空'})

    synonyms = load_synonyms()
    synonyms[word] = synonyms_list
    save_synonyms(synonyms)

    if matcher:
        matcher.update_synonyms(synonyms)

    return jsonify({'success': True, 'message': '更新成功'})


@app.route('/api/delete_synonym', methods=['POST'])
def delete_synonym():
    """删除同义词"""
    data = request.get_json()
    word = data.get('word', '').strip()

    synonyms = load_synonyms()
    if word in synonyms:
        del synonyms[word]
        save_synonyms(synonyms)
        if matcher:
            matcher.update_synonyms(synonyms)
        return jsonify({'success': True, 'message': '删除成功'})

    return jsonify({'success': False, 'message': '同义词不存在'})


# =============== 解析模板管理 ===============

def load_templates():
    """加载解析模板库"""
    templates_file = os.path.join(app.config['UPLOAD_FOLDER'], 'parse_templates.json')
    if os.path.exists(templates_file):
        with open(templates_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'templates': []}


def upsert_template_record(template_payload):
    """新增或更新模板记录"""
    if not template_payload or not template_payload.get('name'):
        return None

    templates_data = load_templates()
    templates = templates_data.setdefault('templates', [])

    for idx, template in enumerate(templates):
        if template.get('name') == template_payload.get('name'):
            templates[idx] = template_payload
            save_templates(templates_data)
            return template_payload

    templates.append(template_payload)
    save_templates(templates_data)
    return template_payload


def save_templates(templates_data):
    """保存解析模板库"""
    templates_file = os.path.join(app.config['UPLOAD_FOLDER'], 'parse_templates.json')
    with open(templates_file, 'w', encoding='utf-8') as f:
        json.dump(templates_data, f, ensure_ascii=False, indent=2)


@app.route('/api/get_templates', methods=['GET'])
def get_templates():
    """获取所有解析模板"""
    templates_data = load_templates()
    return jsonify({
        'success': True,
        'templates': templates_data.get('templates', [])
    })


@app.route('/api/save_template', methods=['POST'])
def save_template():
    """保存解析模板"""
    global parse_result_cache

    data = request.get_json() or {}
    name = data.get('name', '').strip()
    column_mapping = data.get('column_mapping', {})
    header_rows = data.get('header_rows', 1)
    identifiers = data.get('identifiers', [])  # 用于匹配模板的关键词

    if not name:
        return jsonify({'success': False, 'message': '模板名称不能为空'})

    confirmed_mapping = {}
    for col_idx, col_type in (column_mapping or {}).items():
        try:
            confirmed_mapping[int(col_idx)] = col_type
        except (TypeError, ValueError):
            continue

    if not confirmed_mapping:
        return jsonify({'success': False, 'message': '请先选择要保存的列映射'})

    source_type = data.get('source_type') or ((parse_result_cache or {}).get('source') or 'excel')
    parse_result = dict(parse_result_cache or {})
    parse_result.setdefault('header_rows', header_rows)
    parse_result.setdefault('identifiers', identifiers or [])
    parse_result = SmartQuoteParser.apply_template_learning_to_result(
        parse_result,
        confirmed_mapping,
        source_type=source_type
    )

    templates_data = load_templates()
    templates = templates_data.setdefault('templates', [])

    existing_template = None
    for template in templates:
        if template.get('name') == name:
            existing_template = template
            break

    if existing_template is not None:
        template_payload = SmartQuoteParser.register_template_usage_for_result(
            existing_template,
            parse_result,
            confirmed_mapping,
            source_type=source_type,
            manual_save=True,
            template_hit=True
        )
        message = f'模板 "{name}" 已更新'
    else:
        template_payload = SmartQuoteParser.build_template_payload_from_result(
            parse_result,
            name,
            confirmed_mapping,
            source_type=source_type,
            manual_save=True,
            template_hit=True,
            previous_mapping=parse_result.get('last_confirmed_mapping') or parse_result.get('column_mapping') or {}
        )
        message = f'模板 "{name}" 保存成功'

    upsert_template_record(template_payload)

    if parse_result_cache is not None:
        parse_result_cache = parse_result
        parse_result_cache['matched_template'] = template_payload

    return jsonify({
        'success': True,
        'message': message,
        'template': template_payload
    })



@app.route('/api/delete_template', methods=['POST'])
def delete_template():
    """删除解析模板"""
    data = request.get_json()
    name = data.get('name', '').strip()

    templates_data = load_templates()
    original_count = len(templates_data['templates'])
    templates_data['templates'] = [t for t in templates_data['templates'] if t['name'] != name]

    if len(templates_data['templates']) < original_count:
        save_templates(templates_data)
        return jsonify({'success': True, 'message': f'模板 "{name}" 已删除'})

    return jsonify({'success': False, 'message': '模板不存在'})


# =============== 报价历史记录 ===============

@app.route('/api/get_quote_history', methods=['GET'])
def get_quote_history():
    """获取报价历史记录列表"""
    if quote_db is None:
        return jsonify({'success': False, 'message': '数据库未初始化'})

    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)

    history = quote_db.get_history_list(limit, offset)

    return jsonify({
        'success': True,
        'history': history,
        'count': len(history)
    })


@app.route('/api/get_quote_detail/<int:quote_id>', methods=['GET'])
def get_quote_detail(quote_id):
    """获取报价详情"""
    if quote_db is None:
        return jsonify({'success': False, 'message': '数据库未初始化'})

    detail = quote_db.get_quote_detail(quote_id)

    if detail:
        return jsonify({
            'success': True,
            'detail': detail
        })
    else:
        return jsonify({'success': False, 'message': '记录不存在'})


@app.route('/api/save_quote_history', methods=['POST'])
def save_quote_history():
    """保存报价历史记录"""
    global quote_db, match_results, quote_items

    if quote_db is None:
        return jsonify({'success': False, 'message': '数据库未初始化'})

    data = request.get_json()
    customer_name = data.get('customer_name', '')
    export_file = data.get('export_file', '')

    # 统计数据
    total_items = len(match_results)
    matched_items = sum(1 for r in match_results if r.get('confirmed') and r.get('action') == 'select')
    total_amount = 0

    # 构建明细
    items = []
    for result in match_results:
        query_item = result.get('query_item', {})
        selected = result.get('selected_product')

        if result.get('confirmed') and result.get('action') == 'select' and selected and selected.get('product'):
            product = selected['product']
            quantity = query_item.get('quantity', 1) or 1
            price = product.get('market_price', 0) or 0
            total_amount += quantity * price

            items.append({
                'item_name': query_item.get('name', ''),
                'item_quantity': quantity,
                'item_unit': query_item.get('unit', ''),
                'item_price': price,
                'budget_price': query_item.get('price', 0),
                'product_name': product.get('name', ''),
                'product_code': product.get('code', ''),
                'supplier': product.get('supplier', ''),
                'match_score': selected.get('score', 0)
            })

    quote_data = {
        'customer_name': customer_name,
        'quote_file': '',
        'total_items': total_items,
        'matched_items': matched_items,
        'total_amount': total_amount,
        'export_file': export_file,
        'items': items
    }

    quote_id = quote_db.save_quote(quote_data)

    return jsonify({
        'success': True,
        'message': '报价记录已保存',
        'quote_id': quote_id
    })


@app.route('/api/delete_quote_history/<int:quote_id>', methods=['DELETE'])
def delete_quote_history(quote_id):
    """删除报价历史记录"""
    if quote_db is None:
        return jsonify({'success': False, 'message': '数据库未初始化'})

    success = quote_db.delete_quote(quote_id)

    if success:
        return jsonify({'success': True, 'message': '记录已删除'})
    else:
        return jsonify({'success': False, 'message': '删除失败'})


@app.route('/api/get_quote_statistics', methods=['GET'])
def get_quote_statistics():
    """获取报价统计数据"""
    if quote_db is None:
        return jsonify({'success': False, 'message': '数据库未初始化'})

    stats = quote_db.get_statistics()

    return jsonify({
        'success': True,
        'statistics': stats
    })


# =============== AI服务接口 ===============

@app.route('/api/ai/status', methods=['GET'])
def ai_status():
    """获取AI服务状态"""
    global ai_service

    if ai_service is None:
        return jsonify({
            'success': True,
            'enabled': False,
            'provider': 'none',
            'available': False,
            'fallback_mode': True,
            'message': 'AI服务未初始化'
        })

    status = ai_service.get_status()
    status['success'] = True
    return jsonify(status)


@app.route('/api/ai/toggle', methods=['POST'])
def ai_toggle():
    """开关AI功能"""
    global ai_service, use_ai_matcher

    data = request.get_json()
    enabled = data.get('enabled', True)

    if ai_service:
        ai_service.toggle(enabled)

    use_ai_matcher = enabled

    return jsonify({
        'success': True,
        'enabled': enabled,
        'message': f"AI功能已{'开启' if enabled else '关闭'}"
    })


@app.route('/api/ai/chat', methods=['POST'])
def ai_chat():
    """AI对话助手"""
    global ai_service, match_results, quote_items, products_data

    if ai_service is None or not ai_service.is_available():
        return jsonify({
            'success': False,
            'message': 'AI服务不可用，请检查API配置'
        })

    data = request.get_json()
    messages = data.get('messages', [])

    # 构建上下文
    context = {
        'products_count': len(products_data) if products_data else 0,
        'products_source': products_data_source,
        'match_results': match_results[:3] if match_results else [],
        'current_item': match_results[0].get('query_item') if match_results else None
    }

    try:
        # 使用asyncio运行异步方法
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        response = loop.run_until_complete(ai_service.chat(messages, context))
        loop.close()

        return jsonify({
            'success': True,
            'response': response
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'AI对话失败: {str(e)}'
        })


@app.route('/api/ai/explain_match/<int:item_index>', methods=['GET'])
def ai_explain_match(item_index):
    """AI解释匹配结果"""
    global ai_service, match_results

    if ai_service is None or not ai_service.is_available():
        return jsonify({
            'success': False,
            'message': 'AI服务不可用'
        })

    if item_index >= len(match_results):
        return jsonify({'success': False, 'message': '无效的索引'})

    result = match_results[item_index]
    query_item = result.get('query_item', {})
    best_match = result.get('best_match')

    try:
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        explanation = loop.run_until_complete(
            ai_service.explain_match(query_item, best_match)
        )
        loop.close()

        return jsonify({
            'success': True,
            'explanation': explanation
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'解释生成失败: {str(e)}'
        })


@app.route('/api/ai/recommend', methods=['POST'])
def ai_recommend():
    """AI智能推荐替代品"""
    global ai_service, match_results

    if ai_service is None or not ai_service.is_available():
        return jsonify({
            'success': False,
            'message': 'AI服务不可用'
        })

    data = request.get_json()
    item_index = data.get('item_index', 0)

    if item_index >= len(match_results):
        return jsonify({'success': False, 'message': '无效的索引'})

    result = match_results[item_index]
    query_item = result.get('query_item', {})
    matches = result.get('matches', [])[:5]

    try:
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        recommendations = loop.run_until_complete(
            ai_service.recommend_alternatives(query_item, matches)
        )
        loop.close()

        return jsonify({
            'success': True,
            'recommendations': recommendations
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'推荐生成失败: {str(e)}'
        })


@app.route('/api/ai/rematch/<int:item_index>', methods=['POST'])
def ai_rematch_item(item_index):
    """使用AI重新匹配单个项目"""
    global match_results, quote_items, products_data, matcher

    if item_index >= len(quote_items):
        return jsonify({'success': False, 'message': '无效的索引'})

    try:
        # 使用AI匹配器重新匹配
        if AI_AVAILABLE and use_ai_matcher and ai_service and ai_service.is_available():
            ai_matcher = AIProductMatcher(products_data, ai_service)
            new_matches = ai_matcher.match_single(quote_items[item_index], feedback_provider=get_match_feedback_rows)
        else:
            # 降级到传统匹配
            new_matches = matcher.match_single(quote_items[item_index], feedback_provider=get_match_feedback_rows)

        # 更新结果
        match_results[item_index]['matches'] = new_matches
        match_results[item_index]['best_match'] = new_matches[0] if new_matches else None
        match_results[item_index]['ai_enhanced'] = AI_AVAILABLE and use_ai_matcher

        return jsonify({
            'success': True,
            'matches': new_matches,
            'ai_enhanced': AI_AVAILABLE and use_ai_matcher
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'重新匹配失败: {str(e)}'
        })


@app.route('/api/ai/match_all', methods=['POST'])
def ai_match_all():
    """使用AI批量重新匹配"""
    global match_results, quote_items, products_data, matcher

    if not quote_items:
        return jsonify({'success': False, 'message': '没有报价项'})

    try:
        synonyms = load_synonyms()
        match_results = match_quote_items(quote_items, synonyms)

        return jsonify({
            'success': True,
            'match_results': match_results,
            'ai_enhanced': AI_AVAILABLE and use_ai_matcher,
            'count': len(match_results)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'批量匹配失败: {str(e)}'
        })


# =============== PDF导出接口 ===============

# PDF导出模块（可选）
try:
    from utils.pdf_exporter import PDFExporter, create_pdf_exporter
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

# 公司设置文件路径
COMPANY_SETTINGS_FILE = 'data/company_settings.json'


def load_company_settings():
    """加载公司设置"""
    if os.path.exists(COMPANY_SETTINGS_FILE):
        try:
            with open(COMPANY_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {
        'name': '赛正慧采商城',
        'address': '',
        'phone': '',
        'email': '',
        'logo_path': ''
    }


def save_company_settings(settings):
    """保存公司设置"""
    with open(COMPANY_SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


@app.route('/api/pdf/status', methods=['GET'])
def pdf_status():
    """获取PDF导出状态"""
    return jsonify({
        'success': True,
        'available': PDF_AVAILABLE,
        'method': 'weasyprint' if PDF_AVAILABLE else 'none'
    })


@app.route('/api/pdf/export', methods=['POST'])
def export_pdf():
    """导出PDF报价单"""
    global match_results

    if not PDF_AVAILABLE:
        return jsonify({
            'success': False,
            'message': 'PDF导出功能不可用，请安装reportlab或weasyprint'
        })

    data = request.get_json()
    customer_name = data.get('customer_name', '')
    watermark = data.get('watermark', '')
    include_signature = data.get('include_signature', True)

    try:
        # 加载公司设置
        company_settings = load_company_settings()

        # 创建PDF导出器
        exporter = create_pdf_exporter(company_settings)

        # 生成输出路径
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        customer_suffix = f'_{customer_name}' if customer_name else ''
        filename = f'报价单{customer_suffix}_{timestamp}.pdf'
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], filename)

        # 导出PDF
        exporter.export_quote_pdf(
            match_results,
            output_path,
            customer_name=customer_name,
            watermark=watermark,
            include_signature=include_signature
        )

        return jsonify({
            'success': True,
            'message': 'PDF导出成功',
            'filename': filename,
            'download_url': f'/download/{filename}'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'PDF导出失败: {str(e)}'
        })


@app.route('/api/company/settings', methods=['GET'])
def get_company_settings():
    """获取公司设置"""
    settings = load_company_settings()
    return jsonify({
        'success': True,
        'settings': settings
    })


@app.route('/api/company/settings', methods=['POST'])
def update_company_settings():
    """更新公司设置"""
    data = request.get_json()

    settings = load_company_settings()
    settings.update({
        'name': data.get('name', settings.get('name', '')),
        'address': data.get('address', settings.get('address', '')),
        'phone': data.get('phone', settings.get('phone', '')),
        'email': data.get('email', settings.get('email', '')),
        'logo_path': data.get('logo_path', settings.get('logo_path', ''))
    })

    save_company_settings(settings)

    return jsonify({
        'success': True,
        'message': '设置已保存'
    })


@app.route('/api/statistics/dashboard', methods=['GET'])
def get_dashboard_statistics():
    """获取仪表盘统计数据"""
    global products_data, match_results

    # 商品库统计
    products_count = len(products_data) if products_data else 0

    # 分类统计
    category_stats = {}
    if products_data:
        for p in products_data:
            cat = p.get('category', '其他')
            # 提取主分类
            main_cat = cat.split('ξ')[0] if 'ξ' in cat else cat.split('|')[0]
            category_stats[main_cat] = category_stats.get(main_cat, 0) + 1

    # 价格区间统计
    price_ranges = {
        '0-50元': 0,
        '50-100元': 0,
        '100-200元': 0,
        '200-500元': 0,
        '500元以上': 0
    }
    if products_data:
        for p in products_data:
            price = p.get('market_price', 0) or 0
            if price < 50:
                price_ranges['0-50元'] += 1
            elif price < 100:
                price_ranges['50-100元'] += 1
            elif price < 200:
                price_ranges['100-200元'] += 1
            elif price < 500:
                price_ranges['200-500元'] += 1
            else:
                price_ranges['500元以上'] += 1

    # 匹配统计
    match_stats = {
        'total': len(match_results) if match_results else 0,
        'matched': 0,
        'pending': 0,
        'unmatched': 0
    }
    if match_results:
        for r in match_results:
            action = r.get('action', '')
            confirmed = bool(r.get('confirmed'))
            if confirmed and action == 'select':
                match_stats['matched'] += 1
            elif confirmed and action in ['no_match', 'ask_boss']:
                match_stats['unmatched'] += 1
            else:
                match_stats['pending'] += 1

    return jsonify({
        'success': True,
        'products_count': products_count,
        'category_stats': category_stats,
        'price_ranges': price_ranges,
        'match_stats': match_stats
    })


# =============== 商品图片接口 ===============

def _stream_remote_image(response):
    try:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                yield chunk
    finally:
        response.close()


def _placeholder_image_response():
    response = Response(ProductImageHandler.get_placeholder_svg(), mimetype='image/svg+xml')
    response.headers['Cache-Control'] = 'public, max-age=300'
    return response


def _get_runtime_product_images(product):
    images = []
    for image in (product.get('images') or []):
        if not isinstance(image, dict):
            continue
        proxy_url = _normalize_text_value(image.get('proxy_url'))
        source_url = _normalize_text_value(image.get('source_url') or image.get('url'))
        image_url = proxy_url or _normalize_text_value(image.get('url')) or source_url
        if not image_url:
            continue
        images.append({
            **image,
            'url': image_url,
            'proxy_url': proxy_url or image_url,
            'source_url': source_url or image_url,
        })

    if images:
        return images

    fallback_url = _normalize_text_value(product.get('image_url')) or _normalize_text_value(product.get('source_image_url'))
    if fallback_url:
        return [{
            'title': _normalize_text_value(product.get('name')) or '商品图片',
            'url': fallback_url,
            'proxy_url': fallback_url,
            'source_url': _normalize_text_value(product.get('source_image_url')) or fallback_url,
            'product_id': _normalize_text_value(product.get('product_id')),
        }]

    return []


def _build_runtime_product_image_payload(product):
    images = _get_runtime_product_images(product)
    primary = images[0] if images else {}
    return {
        'success': True,
        'image_url': primary.get('proxy_url') or primary.get('url') or '',
        'source_image_url': primary.get('source_url') or primary.get('url') or '',
        'images': images,
        'product_id': str(product.get('product_id', '') or '')
    }


def _build_runtime_product_image_redirect(product, index=0):
    images = _get_runtime_product_images(product)
    if not images:
        return None

    target_index = min(max(int(index or 0), 0), len(images) - 1)
    target_url = _normalize_text_value(
        images[target_index].get('proxy_url')
        or images[target_index].get('url')
        or images[target_index].get('source_url')
    )
    if not target_url:
        return None

    proxied = redirect(target_url, code=302)
    proxied.headers['X-Image-Source'] = target_url
    proxied.headers['Cache-Control'] = 'public, max-age=3600'
    return proxied


@app.route('/api/product/image/<product_code>', methods=['GET'])
def get_product_image(product_code):
    """获取商品图片URL"""
    global products_data

    if not products_data:
        return jsonify({'success': False, 'message': '商品库未加载'})

    product = ProductImageHandler.find_product_by_code(products_data, product_code)
    if not product:
        return jsonify({'success': False, 'message': '商品不存在'})

    if product.get('source') == 'postgres_v2' or products_data_source == 'postgres_v2':
        return jsonify(_build_runtime_product_image_payload(product))

    return jsonify(ProductImageHandler.get_image_api_payload(product))


@app.route('/api/product/image-proxy/<product_code>', methods=['GET'])
def proxy_product_image(product_code):
    """代理返回商品图片，绕过外链图片直接加载失败问题"""
    global products_data

    if not products_data:
        return _placeholder_image_response()

    product = ProductImageHandler.find_product_by_code(products_data, product_code)
    if not product:
        return _placeholder_image_response()

    index = request.args.get('index', default=0, type=int)
    if product.get('source') == 'postgres_v2' or products_data_source == 'postgres_v2':
        pg_response = _build_runtime_product_image_redirect(product, index=index)
        if pg_response is not None:
            return pg_response

    response, target_url = ProductImageHandler.resolve_image_response(product, index=index)
    if response is None:
        return _placeholder_image_response()

    content_type = response.headers.get('content-type', 'image/jpeg')
    proxied = Response(stream_with_context(_stream_remote_image(response)), mimetype=content_type)
    content_length = response.headers.get('content-length')
    if content_length:
        proxied.headers['Content-Length'] = content_length
    if target_url:
        proxied.headers['X-Image-Source'] = target_url
    proxied.headers['Cache-Control'] = 'public, max-age=3600'
    return proxied


@app.route('/api/product/image-proxy/by-id/<product_id>', methods=['GET'])
def proxy_product_image_by_id(product_id):
    """按商城商品ID代理返回图片"""
    global products_data

    if not products_data:
        return _placeholder_image_response()

    product = ProductImageHandler.find_product_by_id(products_data, product_id)
    if not product:
        return _placeholder_image_response()

    index = request.args.get('index', default=0, type=int)
    if product.get('source') == 'postgres_v2' or products_data_source == 'postgres_v2':
        pg_response = _build_runtime_product_image_redirect(product, index=index)
        if pg_response is not None:
            return pg_response

    response, target_url = ProductImageHandler.resolve_image_response(product, index=index)
    if response is None:
        return _placeholder_image_response()

    content_type = response.headers.get('content-type', 'image/jpeg')
    proxied = Response(stream_with_context(_stream_remote_image(response)), mimetype=content_type)
    content_length = response.headers.get('content-length')
    if content_length:
        proxied.headers['Content-Length'] = content_length
    if target_url:
        proxied.headers['X-Image-Source'] = target_url
    proxied.headers['Cache-Control'] = 'public, max-age=3600'
    return proxied


@app.route('/api/product/image-debug/<product_code>', methods=['GET'])
def debug_product_image(product_code):
    """调试商品图片解析结果"""
    global products_data

    if not products_data:
        return jsonify({'success': False, 'message': '商品库未加载'})

    product = ProductImageHandler.find_product_by_code(products_data, product_code)
    if not product:
        return jsonify({'success': False, 'message': '商品不存在'})

    if product.get('source') == 'postgres_v2' or products_data_source == 'postgres_v2':
        payload = _build_runtime_product_image_payload(product)
        return jsonify({
            'success': True,
            'product_code': product_code,
            'product_id': product.get('product_id', ''),
            'resolved_image_url': payload.get('image_url', ''),
            'raw_images': payload.get('images', []),
            'proxy_images': payload.get('images', []),
            'image_url': payload.get('image_url', ''),
            'source_image_url': payload.get('source_image_url', '')
        })

    ProductImageHandler.ensure_product_metadata(product)
    images = ProductImageHandler.get_product_images(product, max_images=3)
    proxy_images = ProductImageHandler.get_proxy_images(product, max_images=3)
    resolved = ProductImageHandler.resolve_product_image_url(product)

    return jsonify({
        'success': True,
        'product_code': product_code,
        'product_id': product.get('product_id', ''),
        'resolved_image_url': resolved,
        'raw_images': images,
        'proxy_images': proxy_images,
        'image_url': proxy_images[0].get('url') if proxy_images else '',
        'source_image_url': proxy_images[0].get('source_url') if proxy_images else ''
    })


@app.route('/api/debug/rebuild_product_images', methods=['POST'])
def rebuild_product_images():
    """重建当前内存商品图片字段"""
    global products_data, products_data_source, matcher

    if not products_data:
        return jsonify({'success': False, 'message': '商品库未加载'})

    if products_data_source == 'postgres_v2':
        refreshed_products = _run_async_task(_load_v2_products_for_runtime_async())
        _set_runtime_products_snapshot(refreshed_products, source='postgres_v2')
        return jsonify({
            'success': True,
            'count': len(products_data),
            'products_source': products_data_source
        })

    ProductImageHandler.set_base_url(ProductImageHandler.BASE_URL)
    products_data = [_annotate_product_cost_fields(product, source='loaded') for product in products_data]
    products_data = ProductImageHandler.enrich_products_with_resolved_images(products_data)
    _set_runtime_products_snapshot(products_data, source=products_data_source or 'legacy_json')
    return jsonify({
        'success': True,
        'count': len(products_data),
        'products_source': products_data_source
    })


@app.route('/api/debug/product_lookup/<product_code>', methods=['GET'])
def debug_product_lookup(product_code):
    """查看商城搜索页中该商品的真实图片地址"""
    global products_data

    if not products_data:
        return jsonify({'success': False, 'message': '商品库未加载'})

    product = ProductImageHandler.find_product_by_code(products_data, product_code)
    if not product:
        return jsonify({'success': False, 'message': '商品不存在'})

    keywords = ProductImageHandler._build_search_keywords(product)
    attempts = []
    for keyword in keywords:
        html_text = ProductImageHandler._fetch_search_page(keyword)
        block = ProductImageHandler._locate_product_block(html_text, product)
        attempts.append({
            'keyword': keyword,
            'product_id': ProductImageHandler._extract_product_id_from_search(block, product) if block else '',
            'resolved_image_url': ProductImageHandler._extract_product_image_from_search(block, product) if block else '',
            'block_preview': block[:2000] if block else ''
        })

    resolved_image_url, resolved_product_id = ProductImageHandler._resolve_from_search(product)
    return jsonify({
        'success': True,
        'keywords': keywords,
        'product_id': resolved_product_id,
        'resolved_image_url': resolved_image_url,
        'fallback_image_url': ProductImageHandler._get_fallback_image_url(product),
        'attempts': attempts
    })




# =============== OCR图片识别 ===============

# OCR模块（可选，延迟初始化以避免启动阻塞）
try:
    import easyocr
    OCR_READER = None
    OCR_AVAILABLE = True
except ImportError:
    OCR_READER = None
    OCR_AVAILABLE = False
    print("OCR模块未安装，图片识别功能不可用")


def ensure_ocr_reader():
    global OCR_READER
    if not OCR_AVAILABLE:
        return None
    if OCR_READER is None:
        OCR_READER = easyocr.Reader(['ch_sim', 'en'], gpu=False)
    return OCR_READER




def to_json_safe(value):
    """递归转换numpy类型为Python原生类型，确保可JSON序列化"""
    try:
        import numpy as np
        numpy_integer = np.integer
        numpy_floating = np.floating
        numpy_ndarray = np.ndarray
    except Exception:
        numpy_integer = ()
        numpy_floating = ()
        numpy_ndarray = ()

    if isinstance(value, dict):
        return {str(k): to_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json_safe(v) for v in value]
    if numpy_ndarray and isinstance(value, numpy_ndarray):
        return to_json_safe(value.tolist())
    if numpy_integer and isinstance(value, numpy_integer):
        return int(value)
    if numpy_floating and isinstance(value, numpy_floating):
        return float(value)
    if hasattr(value, 'item') and callable(getattr(value, 'item')):
        try:
            return to_json_safe(value.item())
        except Exception:
            pass
    return value


def build_ocr_parse_result(parsed_items, raw_text):
    """将OCR结果包装成与Excel智能解析一致的结构"""
    candidate_columns = [
        ('seq', '序号'),
        ('name', '产品名称'),
        ('spec', '规格型号'),
        ('color', '颜色'),
        ('unit', '单位'),
        ('quantity', '数量'),
        ('price', '单价'),
        ('brand', '品牌'),
        ('remark', '备注')
    ]

    default_columns = []
    for field, header in candidate_columns:
        if field in ('seq', 'name'):
            default_columns.append((field, header))
            continue

        if any(str(item.get(field, '')).strip() for item in parsed_items):
            default_columns.append((field, header))

    if len(default_columns) <= 2:
        default_columns.extend([
            ('quantity', '数量'),
            ('price', '单价')
        ])

    raw_headers = [header for _, header in default_columns]
    low_confidence_rows = []

    column_mapping = {}
    for idx, (detected_type, original_header) in enumerate(default_columns):
        confidences = [float(item.get('confidence') or 0) for item in parsed_items if str(item.get(detected_type, '')).strip()]
        avg_confidence = (sum(confidences) / len(confidences)) if confidences else 0.95
        column_mapping[idx] = {
            'detected_type': detected_type,
            'confidence': round(avg_confidence, 2),
            'original_header': original_header,
            'needs_confirm': avg_confidence < 0.8
        }

    ocr_rows = []
    identifiers = []
    for row_index, item in enumerate(parsed_items):
        row_confidence = float(item.get('confidence') or 0)
        row_data = {
            'row_index': row_index,
            'confidence': row_confidence,
            'ocr_confidence': row_confidence,
            'low_confidence': row_confidence < 0.75
        }

        if row_data['low_confidence']:
            low_confidence_rows.append(row_index)

        for col_idx, (field, _) in enumerate(default_columns):
            value = item.get(field, '')
            row_data[f'original_col_{col_idx}'] = value
            row_data[field] = value
            if field in ('name', 'spec', 'brand') and str(value).strip():
                identifiers.append(str(value).strip())

        ocr_rows.append(row_data)

    identifiers = identifiers[:20]
    header_signature = '|'.join(str(header).strip().lower() for header in raw_headers if str(header).strip())
    identifier_signature = '|'.join(sorted(str(value).strip().lower() for value in identifiers if str(value).strip())[:20])

    return {
        'source': 'ocr',
        'header_rows': 1,
        'data_start_row': 0,
        'raw_headers': raw_headers,
        'column_mapping': column_mapping,
        'preview': ocr_rows[:5],
        'ocr_rows': ocr_rows,
        'ocr_items': parsed_items,
        'raw_text': raw_text,
        'identifiers': identifiers,
        'header_signature': header_signature,
        'identifier_signature': identifier_signature,
        'low_confidence_rows': low_confidence_rows
    }



def _build_ocr_box(line):
    """将OCR返回的框信息标准化"""
    text = str(line.get('text', '')).strip()
    position = line.get('position') or []
    if not text or len(position) < 4:
        return None

    xs = [int(p[0]) for p in position]
    ys = [int(p[1]) for p in position]
    x1, x2 = min(xs), max(xs)
    y1, y2 = min(ys), max(ys)

    return {
        'text': text,
        'confidence': float(line.get('confidence') or 0),
        'position': position,
        'x1': x1,
        'x2': x2,
        'y1': y1,
        'y2': y2,
        'cx': (x1 + x2) / 2,
        'cy': (y1 + y2) / 2,
        'width': max(x2 - x1, 1),
        'height': max(y2 - y1, 1)
    }



def _clean_ocr_number(text):
    """清理OCR识别出的数字文本"""
    if text is None:
        return ''

    cleaned = str(text).strip()
    replacements = {
        'O': '0',
        'o': '0',
        'I': '1',
        'l': '1',
        '，': ',',
        '。': '.',
        ' ': ''
    }
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)

    return cleaned



def _is_numeric_like(text):
    cleaned = _clean_ocr_number(text)
    return bool(cleaned and __import__('re').fullmatch(r'\d+(?:\.\d+)?', cleaned))



def _parse_numeric_value(text):
    cleaned = _clean_ocr_number(text)
    if not cleaned:
        return None

    try:
        number = float(cleaned)
        return int(number) if number.is_integer() else number
    except ValueError:
        return None



def _merge_ocr_texts(boxes):
    """合并同一列的多段OCR文本"""
    ordered = sorted(boxes, key=lambda item: (item['y1'], item['x1']))
    parts = []
    for box in ordered:
        text = str(box.get('text', '')).strip()
        if not text:
            continue
        if parts and parts[-1] == text:
            continue
        parts.append(text)

    if not parts:
        return ''

    merged = parts[0]
    for part in parts[1:]:
        if (merged and merged[-1].isascii() and merged[-1].isalnum() and
                part and part[0].isascii() and part[0].isalnum()):
            merged += ' ' + part
        else:
            merged += ' ' + part

    return merged.strip()



def _cluster_row_boxes_by_x(boxes, tolerance=45):
    """按x坐标聚合同一行中的单元格文本"""
    clusters = []
    for box in sorted(boxes, key=lambda item: item['cx']):
        target_cluster = None
        for cluster in clusters:
            if abs(box['cx'] - cluster['cx']) <= tolerance:
                target_cluster = cluster
                break

        if target_cluster is None:
            target_cluster = {
                'boxes': [],
                'cx': box['cx']
            }
            clusters.append(target_cluster)

        target_cluster['boxes'].append(box)
        target_cluster['cx'] = sum(item['cx'] for item in target_cluster['boxes']) / len(target_cluster['boxes'])

    return sorted(clusters, key=lambda item: item['cx'])



def _fallback_parse_ocr_results(text_lines):
    """无定位信息时的兜底OCR解析"""
    items = []
    import re

    price_pattern = r'(?:￥|¥|价格|单价)?[\s]*(\d+\.?\d*)[\s]*(?:元|￥)?'
    current_seq = 0

    for line in text_lines:
        text = str(line.get('text', '')).strip()
        if any(kw in text for kw in ['序号', '编号', '名称', '商品名称', '数量', '单位', '价格', '单价', '总价', '备注', '合计', '总计', '小计']):
            continue
        if len(text) < 2:
            continue

        seq_match = re.match(r'^(\d{1,3})[\s\.]+', text)
        if seq_match:
            current_seq = int(seq_match.group(1))
            text = text[len(seq_match.group(0)):].strip()

        price_match = re.search(price_pattern, text)
        if not price_match:
            continue

        try:
            price = float(price_match.group(1))
        except ValueError:
            continue

        if not (0 < price < 100000):
            continue

        name_part = str(text[:price_match.start()].strip())
        if not name_part or len(name_part) <= 1:
            continue

        qty_match = re.search(r'(\d+)[\s]*(?:个|件|套|盒|包|箱|只|双|台|张|本|支|瓶|罐|桶|袋|卷|米|公斤|kg|g)', name_part, re.IGNORECASE)
        quantity = 1
        if qty_match:
            quantity = int(qty_match.group(1))
            name_part = str(name_part[:qty_match.start()].strip())

        items.append({
            'seq': int(current_seq or len(items) + 1),
            'name': str(name_part),
            'quantity': int(quantity),
            'price': float(price),
            'confidence': float(line.get('confidence') or 0)
        })

    return items[:50]



def _group_ocr_text_rows(boxes):
    """按y坐标聚合OCR文本行"""
    if not boxes:
        return []

    avg_height = sum(box['height'] for box in boxes) / len(boxes)
    tolerance = max(18, avg_height * 0.7)
    rows = []

    for box in sorted(boxes, key=lambda item: item['cy']):
        target_row = None
        for row in rows:
            if abs(box['cy'] - row['cy']) <= tolerance:
                target_row = row
                break

        if target_row is None:
            target_row = {'boxes': [], 'cy': box['cy']}
            rows.append(target_row)

        target_row['boxes'].append(box)
        target_row['cy'] = sum(item['cy'] for item in target_row['boxes']) / len(target_row['boxes'])

    for row in rows:
        row['boxes'] = sorted(row['boxes'], key=lambda item: item['x1'])

    return sorted(rows, key=lambda item: item['cy'])



def _detect_table_right(boxes, image_width):
    """估算主表格右边界，排除右侧备注区"""
    numeric_candidates = [
        box for box in boxes
        if _is_numeric_like(box['text']) and image_width * 0.65 <= box['cx'] <= image_width * 0.82
    ]
    if numeric_candidates:
        return max(box['x2'] for box in numeric_candidates) + 12
    return image_width * 0.78



def _parse_table_rows_from_boxes(boxes):
    """基于OCR框位置重建逻辑表格行"""
    if not boxes:
        return []

    image_width = max(box['x2'] for box in boxes)
    table_right = _detect_table_right(boxes, image_width)
    table_boxes = [box for box in boxes if box['x1'] <= table_right]
    text_rows = _group_ocr_text_rows(table_boxes)
    if not text_rows:
        return []

    logical_rows = []
    current = None

    seq_limit = table_right * 0.10
    name_limit_left = table_right * 0.10
    name_limit_right = table_right * 0.32
    qty_limit_left = table_right * 0.90

    for row in text_rows:
        row_boxes = row['boxes']
        has_seq = any(box['x2'] <= seq_limit and _is_numeric_like(box['text']) for box in row_boxes)
        has_name = any(name_limit_left <= box['cx'] <= name_limit_right for box in row_boxes)
        has_qty = any(box['cx'] >= qty_limit_left and _is_numeric_like(box['text']) for box in row_boxes)
        is_start = has_qty and (has_seq or has_name)

        if is_start:
            if current and current['boxes']:
                logical_rows.append(current)
            current = {
                'boxes': list(row_boxes),
                'table_right': table_right
            }
        elif current is not None:
            current['boxes'].extend(row_boxes)

    if current and current['boxes']:
        logical_rows.append(current)

    return logical_rows



def parse_ocr_results(text_lines: list) -> list:
    """解析OCR结果，优先按表格行列还原报价项"""
    boxes = []
    for line in text_lines:
        box = _build_ocr_box(line)
        if box is not None:
            boxes.append(box)

    table_rows = _parse_table_rows_from_boxes(boxes)
    items = []

    for row_index, row in enumerate(table_rows):
        row_boxes = sorted(row['boxes'], key=lambda item: (item['y1'], item['x1']))
        table_right = row.get('table_right') or max(box['x2'] for box in row_boxes)

        seq_boxes = [box for box in row_boxes if box['x2'] <= table_right * 0.10 and _is_numeric_like(box['text'])]
        qty_boxes = [box for box in row_boxes if box['cx'] >= table_right * 0.90 and _is_numeric_like(box['text'])]
        name_boxes = [box for box in row_boxes if table_right * 0.10 <= box['cx'] <= table_right * 0.32]
        spec_boxes = [box for box in row_boxes if table_right * 0.32 < box['cx'] <= table_right * 0.68]
        color_boxes = [box for box in row_boxes if table_right * 0.68 < box['cx'] <= table_right * 0.80]
        unit_boxes = [box for box in row_boxes if table_right * 0.80 < box['cx'] <= table_right * 0.90 and not _is_numeric_like(box['text'])]

        seq_value = _parse_numeric_value(seq_boxes[0]['text']) if seq_boxes else row_index + 1
        quantity_value = _parse_numeric_value(qty_boxes[-1]['text']) if qty_boxes else None
        name_text = _merge_ocr_texts(name_boxes)
        spec_text = _merge_ocr_texts(spec_boxes)
        color_text = _merge_ocr_texts(color_boxes)
        unit_text = _merge_ocr_texts(unit_boxes)

        merged_text = ' '.join(filter(None, [name_text, spec_text, color_text, unit_text]))
        if any(keyword in merged_text for keyword in ['序号', '名称', '规格', '型号', '颜色', '单位', '数量', '备注']):
            continue

        if not name_text or quantity_value is None:
            continue

        row_confidences = [box['confidence'] for box in row_boxes if box.get('confidence') is not None]
        avg_confidence = sum(row_confidences) / len(row_confidences) if row_confidences else 0

        items.append({
            'seq': int(seq_value),
            'name': name_text,
            'spec': spec_text,
            'color': color_text,
            'unit': unit_text,
            'quantity': quantity_value,
            'confidence': float(round(avg_confidence, 2))
        })

    if items:
        return items[:50]

    return _fallback_parse_ocr_results(text_lines)


def normalize_quote_value(col_type, value):
    """按字段类型规范化OCR提取值"""
    if value is None:
        return ''

    if isinstance(value, str):
        value = value.strip()

    if value == '':
        return ''

    if col_type in ('quantity', 'price'):
        try:
            number = float(str(value).replace(',', ''))
            if col_type == 'quantity' and number.is_integer():
                return int(number)
            return number
        except (TypeError, ValueError):
            return value

    if col_type == 'seq':
        try:
            return int(float(str(value)))
        except (TypeError, ValueError):
            return value

    return value


def get_ocr_parsed_items(ocr_rows, confirmed_mapping):
    """根据用户确认的映射，从OCR缓存行中提取报价项"""
    type_columns = {}
    for col_idx, col_type in sorted(confirmed_mapping.items()):
        if col_type:
            type_columns.setdefault(col_type, []).append(col_idx)

    items = []
    for row_index, row in enumerate(ocr_rows):
        item = {
            'row_index': row.get('row_index', row_index),
            'source_type': 'ocr',
            'ocr_confidence': float(row.get('ocr_confidence') or row.get('confidence') or 0),
            'low_confidence': bool(row.get('low_confidence'))
        }

        for col_type, col_indices in type_columns.items():
            item[col_type] = ''
            for col_idx in col_indices:
                value = row.get(f'original_col_{col_idx}', '')
                if value is not None and str(value).strip():
                    item[col_type] = normalize_quote_value(col_type, value)
                    break

        if item.get('name') and str(item['name']).strip():
            items.append(normalize_quote_item(item))

    return items


@app.route('/api/ocr/status', methods=['GET'])
def ocr_status():
    """获取OCR服务状态"""
    return jsonify({
        'success': True,
        'available': OCR_AVAILABLE,
        'build': APP_BUILD
    })


@app.route('/api/ocr/recognize', methods=['POST'])
def ocr_recognize():
    """OCR识别上传的图片"""
    global smart_parser, parse_result_cache

    reader = ensure_ocr_reader()
    if reader is None:
        return jsonify({
            'success': False,
            'message': 'OCR服务不可用，请安装easyocr: pip install easyocr'
        })

    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '没有选择文件'})

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': '没有选择文件'})

    try:
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name

        results = reader.readtext(tmp_path)
        os.unlink(tmp_path)

        text_lines = []
        for (bbox, text, confidence) in results:
            if float(confidence) > 0.3:
                position = [[int(p[0]), int(p[1])] for p in bbox]
                text_lines.append({
                    'text': str(text),
                    'confidence': float(round(confidence, 2)),
                    'position': position
                })

        parsed_items = parse_ocr_results(text_lines)
        parse_result = _prepare_ocr_parse_result(parsed_items, text_lines)

        smart_parser = None
        parse_result_cache = parse_result

        payload = {
            'success': True,
            'build': APP_BUILD,
            'raw_text': text_lines,
            'parsed_items': parsed_items,
            'count': int(len(parsed_items)),
            'parse_result': parse_result
        }
        import json
        safe_payload = to_json_safe(payload)
        return app.response_class(
            response=json.dumps(safe_payload, ensure_ascii=False),
            status=200,
            mimetype='application/json'
        )

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'OCR识别失败: {str(e)}'
        })




# =============== 报价单在线分享 ===============

import uuid
import time

# 在线分享存储（生产环境应使用数据库）
share_cache = {}


@app.route('/api/share/create', methods=['POST'])
def create_share_link():
    """创建报价单分享链接"""
    global match_results, quote_items

    if not match_results:
        return jsonify({'success': False, 'message': '没有可分享的报价单'})

    data = request.get_json()
    customer_name = data.get('customer_name', '')
    expire_hours = data.get('expire_hours', 24)

    # 生成分享ID
    share_id = str(uuid.uuid4())[:8].upper()

    # 存储分享数据
    share_data = {
        'id': share_id,
        'match_results': match_results,
        'quote_items': quote_items,
        'customer_name': customer_name,
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'expire_at': time.time() + expire_hours * 3600,
        'views': 0
    }

    share_cache[share_id] = share_data

    # 生成分享链接
    share_url = f"{request.host_url}share/{share_id}"

    return jsonify({
        'success': True,
        'share_id': share_id,
        'share_url': share_url,
        'expire_hours': expire_hours
    })


@app.route('/share/<share_id>', methods=['GET'])
def view_shared_quote(share_id):
    """查看分享的报价单"""
    share_data = share_cache.get(share_id)

    if not share_data:
        return render_template('error.html', message='分享链接不存在或已过期'), 404

    if time.time() > share_data['expire_at']:
        return render_template('error.html', message='分享链接已过期'), 410

    # 更新浏览次数
    share_data['views'] += 1

    return render_template('share.html',
                         share_id=share_id,
                         share_data=share_data)


@app.route('/api/share/<share_id>', methods=['GET'])
def get_share_data(share_id):
    """获取分享数据API"""
    share_data = share_cache.get(share_id)

    if not share_data:
        return jsonify({'success': False, 'message': '分享链接不存在或已过期'})

    if time.time() > share_data['expire_at']:
        return jsonify({'success': False, 'message': '分享链接已过期'})

    return jsonify({
        'success': True,
        'data': {
            'customer_name': share_data['customer_name'],
            'created_at': share_data['created_at'],
            'views': share_data['views'],
            'match_results': share_data['match_results']
        }
    })


# =============== 合同生成 ===============

@app.route('/api/contract/generate', methods=['POST'])
def generate_contract():
    """生成采购合同"""
    global match_results

    if not match_results:
        return jsonify({'success': False, 'message': '没有报价数据'})

    data = request.get_json()
    customer_name = data.get('customer_name', '')
    customer_contact = data.get('customer_contact', '')
    customer_address = data.get('customer_address', '')

    # 生成合同编号
    contract_no = f"HT{datetime.now().strftime('%Y%m%d%H%M%S')}"

    # 计算总金额
    total_amount = 0
    for result in match_results:
        if result.get('confirmed') and result.get('action') == 'select' and result.get('selected_product'):
            product = result['selected_product'].get('product', {})
            quantity = result.get('query_item', {}).get('quantity', 0) or 0
            price = product.get('market_price', 0) or 0
            total_amount += quantity * price

    try:
        # 生成合同PDF
        output_path = generate_contract_pdf(
            match_results,
            contract_no,
            customer_name,
            customer_contact,
            customer_address,
            total_amount
        )

        filename = os.path.basename(output_path)

        return jsonify({
            'success': True,
            'contract_no': contract_no,
            'filename': filename,
            'download_url': f'/download/{filename}',
            'total_amount': total_amount
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'合同生成失败: {str(e)}'
        })


def generate_contract_pdf(match_results, contract_no, customer_name, customer_contact, customer_address, total_amount):
    """生成合同PDF文件"""
    from utils.pdf_exporter import PDFExporter

    company_settings = load_company_settings()
    exporter = PDFExporter(company_settings)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'采购合同_{customer_name}_{timestamp}.pdf'
    output_path = os.path.join(app.config['OUTPUT_FOLDER'], filename)

    # 使用reportlab生成合同
    if exporter.reportlab_available:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib import colors

        doc = SimpleDocTemplate(output_path, pagesize=A4,
                                rightMargin=2*cm, leftMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2*cm)

        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        try:
            pdfmetrics.registerFont(TTFont('SimSun', 'simsun.ttc'))
            font_name = 'SimSun'
        except:
            font_name = 'Helvetica'

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('Title', fontName=font_name, fontSize=18, alignment=1, spaceAfter=20)
        body_style = ParagraphStyle('Body', fontName=font_name, fontSize=10, leading=18)

        elements = []

        # 合同标题
        elements.append(Paragraph('采购合同', title_style))
        elements.append(Spacer(1, 0.5*cm))

        # 合同编号
        elements.append(Paragraph(f'合同编号：{contract_no}', body_style))
        elements.append(Spacer(1, 0.3*cm))

        # 甲乙双方
        elements.append(Paragraph(f'甲方（采购方）：{customer_name}', body_style))
        elements.append(Paragraph(f'联系人：{customer_contact}', body_style))
        elements.append(Paragraph(f'地址：{customer_address}', body_style))
        elements.append(Spacer(1, 0.3*cm))

        company_name = company_settings.get('name', '赛正慧采商城')
        elements.append(Paragraph(f'乙方（供货方）：{company_name}', body_style))
        elements.append(Spacer(1, 0.5*cm))

        # 商品明细表
        table_data = [['序号', '商品名称', '数量', '单价', '金额']]

        for i, result in enumerate(match_results, 1):
            if result.get('confirmed') and result.get('action') == 'select' and result.get('selected_product'):
                query = result.get('query_item', {})
                product = result['selected_product'].get('product', {})
                quantity = query.get('quantity', 0) or 0
                price = product.get('market_price', 0) or 0
                subtotal = quantity * price

                table_data.append([
                    str(i),
                    product.get('name', '')[:20],
                    str(quantity),
                    f'¥{price:.2f}',
                    f'¥{subtotal:.2f}'
                ])

        table_data.append(['', '', '', '合计：', f'¥{total_amount:,.2f}'])

        table = Table(table_data, colWidths=[1*cm, 7*cm, 2*cm, 2.5*cm, 2.5*cm])
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), font_name),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6366f1')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -2), 0.5, colors.grey),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f0fdf4')),
        ]))

        elements.append(table)
        elements.append(Spacer(1, 1*cm))

        # 条款
        elements.append(Paragraph('双方约定：', body_style))
        elements.append(Paragraph('1. 交货时间：合同签订后7个工作日内', body_style))
        elements.append(Paragraph('2. 付款方式：款到发货', body_style))
        elements.append(Paragraph('3. 质量保证：产品符合国家标准', body_style))
        elements.append(Spacer(1, 1*cm))

        # 签章区
        elements.append(Paragraph('甲方签章：________________', body_style))
        elements.append(Spacer(1, 0.5*cm))
        elements.append(Paragraph('乙方签章：________________', body_style))
        elements.append(Spacer(1, 0.3*cm))
        elements.append(Paragraph(f'日期：{datetime.now().strftime("%Y年%m月%d日")}', body_style))

        doc.build(elements)

    return output_path


# =============== 启动 ===============

def init_ai_service():
    """初始化AI服务"""
    global ai_service

    if AI_AVAILABLE:
        try:
            ai_service = get_ai_service()
            if ai_service.is_available():
                print(f"AI服务已启动: {ai_service.get_provider_name()}")
            else:
                print("AI服务不可用，将使用传统匹配")
        except Exception as e:
            print(f"AI服务初始化失败: {e}")
            ai_service = None
    else:
        print("AI模块未安装，使用传统匹配")


if __name__ == '__main__':
    # 确保文件夹存在
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

    # 初始化数据库
    db_path = os.path.join(app.config['UPLOAD_FOLDER'], 'quote_history.db')
    quote_db = QuoteHistoryDB(db_path)

    # 预加载商品库
    load_products()

    # 初始化AI服务
    init_ai_service()

    print("=" * 50)
    print("一键报价系统启动中...")
    print("AI增强: " + ("已启用" if ai_service and ai_service.is_available() else "未启用"))
    print("请访问: http://localhost:5000")
    print("=" * 50)

    app.run(debug=True, host='127.0.0.1', port=5000, use_reloader=False)
