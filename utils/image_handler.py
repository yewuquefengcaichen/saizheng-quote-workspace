# -*- coding: utf-8 -*-
"""
商品图片处理模块
功能：从商品intro字段提取图片URL，生成完整图片链接
"""

import html
import logging
import re
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class ProductImageHandler:
    """商品图片处理器"""

    BASE_URL = "https://sz.dinghuovip.com"
    FILE_BASE_URL = "https://udeanfile.dinghuovip.com"
    REQUEST_HEADERS = {
        'User-Agent': 'Mozilla/5.0',
        'Referer': f'{BASE_URL}/',
        'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'
    }
    SEARCH_ENDPOINT = '/Product/C_ProductList'
    SEARCH_CONTEXT = {
        'isstock': '0',
        'orderby': 'none',
        'PCProductShow': 'PCProductShowSPU',
        'mId': '7114ea97-d7fb-45af-9aee-e3642678ea41',
        't': '0',
        'aType': '4'
    }
    PRODUCT_INFO_PATTERNS = [
        re.compile(r'/Product/C_ProductInfo\?product(?:I|i)d=(\d+)'),
        re.compile(r'pid="(\d+)"')
    ]
    PRODUCT_IMAGE_PATTERNS = [
        re.compile(r'<img[^>]+src=["\'](https?://[^"\']*?/ProductImg/[^"\']+)["\']', re.I),
        re.compile(r'<img[^>]+src=["\'](/Upload/[^"\']*?/ProductImg/[^"\']+)["\']', re.I)
    ]

    _session = requests.Session()
    _session.headers.update(REQUEST_HEADERS)
    _search_page_cache: Dict[str, str] = {}
    _resolved_image_cache: Dict[str, str] = {}
    _product_id_cache: Dict[str, str] = {}

    @classmethod
    def set_base_url(cls, url: str):
        """设置商城基础URL"""
        cls.BASE_URL = url.rstrip('/')
        cls.REQUEST_HEADERS['Referer'] = f'{cls.BASE_URL}/'
        cls._session.headers.update(cls.REQUEST_HEADERS)
        if 'dinghuovip.com' in cls.BASE_URL and 'udeanfile.' not in cls.BASE_URL:
            cls.FILE_BASE_URL = cls.BASE_URL.replace('://', '://udeanfile.', 1)
        else:
            cls.FILE_BASE_URL = cls.BASE_URL
        cls._search_page_cache.clear()
        cls._resolved_image_cache.clear()
        cls._product_id_cache.clear()
        cls._session.cookies.clear()

    @classmethod
    def _request(cls, url: str, **kwargs):
        timeout = kwargs.pop('timeout', 12)
        return cls._session.get(url, timeout=timeout, **kwargs)

    @classmethod
    def _request_safe(cls, url: str, **kwargs):
        try:
            return cls._request(url, **kwargs)
        except requests.RequestException as exc:
            logger.warning('Image request failed for %s: %s', url, exc)
            return None

    @classmethod
    def _looks_like_image_response(cls, response) -> bool:
        if response is None:
            return False
        content_type = (response.headers.get('content-type') or '').lower()
        return response.status_code == 200 and content_type.startswith('image/')

    @classmethod
    def _get_cache_key(cls, product: Dict) -> str:
        return str(product.get('code') or product.get('name') or '').strip()

    @classmethod
    def _pick_product_search_keyword(cls, product: Dict) -> str:
        for key in ('name', 'model', 'code'):
            value = str(product.get(key, '') or '').strip()
            if value:
                return value
        return ''

    @classmethod
    def _build_search_keywords(cls, product: Dict) -> List[str]:
        keywords = []
        for key in ('code', 'name', 'model'):
            value = str(product.get(key, '') or '').strip()
            if value and value not in keywords:
                keywords.append(value)
        return keywords

    @classmethod
    def _normalize_text(cls, text: str) -> str:
        text = html.unescape(str(text or '')).lower()
        return re.sub(r'[\s\-_（）()\[\]【】/\\.,，。:：;；\'"“”‘’]+', '', text)

    @classmethod
    def _get_match_tokens(cls, product: Dict) -> List[str]:
        tokens = []
        for key in ('code', 'name', 'model'):
            raw_value = str(product.get(key, '') or '').strip()
            if not raw_value:
                continue

            normalized_value = cls._normalize_text(raw_value)
            if normalized_value and normalized_value not in tokens:
                tokens.append(normalized_value)

            for token in re.findall(r'[A-Za-z0-9]+|[\u4e00-\u9fff]{2,}', raw_value):
                normalized_token = cls._normalize_text(token)
                if len(normalized_token) >= 2 and normalized_token not in tokens:
                    tokens.append(normalized_token)

        return tokens

    @classmethod
    def _extract_product_blocks(cls, html_text: str) -> List[str]:
        if not html_text:
            return []

        blocks = re.findall(
            r'(<div class="product_item".*?)(?=<div class="product_item"|<div class="page_search_tool_area"|<script type="text/javascript">)',
            html_text,
            re.S | re.I
        )
        return blocks

    @classmethod
    def _score_product_block(cls, block: str, product: Dict) -> int:
        normalized_block = cls._normalize_text(block)
        if not normalized_block:
            return -1

        score = 0
        code = cls._normalize_text(product.get('code', ''))
        name = cls._normalize_text(product.get('name', ''))
        model = cls._normalize_text(product.get('model', ''))

        if code and code in normalized_block:
            score += 120
        if name and name in normalized_block:
            score += 100
        if model and len(model) >= 3 and model in normalized_block:
            score += 40

        for token in cls._get_match_tokens(product):
            if token in normalized_block:
                score += 8 if len(token) >= 4 else 4

        if re.search(r'/ProductImg/', block, re.I):
            score += 5

        return score

    @classmethod
    def _locate_product_block(cls, html_text: str, product: Dict) -> str:
        if not html_text:
            return ''

        best_block = ''
        best_score = 0
        for block in cls._extract_product_blocks(html_text):
            score = cls._score_product_block(block, product)
            if score > best_score:
                best_score = score
                best_block = block

        if best_block and best_score > 0:
            return best_block

        for needle in (
            str(product.get('name', '') or '').strip(),
            str(product.get('model', '') or '').strip(),
            str(product.get('code', '') or '').strip()
        ):
            if needle and needle in html_text:
                index = html_text.find(needle)
                return html_text[max(0, index - 4000): index + 8000]

        return ''

    @classmethod
    def _fetch_search_page(cls, keyword: str) -> str:
        keyword = (keyword or '').strip()
        if not keyword:
            return ''
        if keyword in cls._search_page_cache:
            return cls._search_page_cache[keyword]

        response = cls._request_safe(
            f'{cls.BASE_URL}{cls.SEARCH_ENDPOINT}',
            params={'search': keyword, **cls.SEARCH_CONTEXT}
        )
        if response is None or response.status_code != 200:
            return ''

        html_text = response.text or ''
        cls._search_page_cache[keyword] = html_text
        return html_text

    @classmethod
    def _extract_product_id_from_search(cls, html_text: str, product: Dict) -> str:
        target_block = cls._locate_product_block(html_text, product)
        for pattern in cls.PRODUCT_INFO_PATTERNS:
            match = pattern.search(target_block)
            if match:
                return match.group(1)
        return ''

    @classmethod
    def _extract_product_image_from_search(cls, html_text: str, product: Dict) -> str:
        target_block = cls._locate_product_block(html_text, product)
        for pattern in cls.PRODUCT_IMAGE_PATTERNS:
            match = pattern.search(target_block)
            if match:
                return cls._normalize_source_url(match.group(1))
        return ''

    @classmethod
    def ensure_product_metadata(cls, product: Dict) -> Dict:
        if not product:
            return product

        cache_key = cls._get_cache_key(product)
        if cache_key in cls._product_id_cache and not product.get('product_id'):
            product['product_id'] = cls._product_id_cache[cache_key]
            return product

        if product.get('product_id'):
            cls._product_id_cache[cache_key] = str(product.get('product_id'))
            return product

        for keyword in cls._build_search_keywords(product):
            html_text = cls._fetch_search_page(keyword)
            product_id = cls._extract_product_id_from_search(html_text, product)
            if product_id:
                product['product_id'] = product_id
                cls._product_id_cache[cache_key] = product_id
                break
        return product

    @classmethod
    def _resolve_from_search(cls, product: Dict):
        for keyword in cls._build_search_keywords(product):
            html_text = cls._fetch_search_page(keyword)
            target_block = cls._locate_product_block(html_text, product)
            if not target_block:
                continue

            image_url = cls._extract_product_image_from_search(target_block, product)
            product_id = cls._extract_product_id_from_search(target_block, product)
            if image_url or product_id:
                return image_url, product_id

        return '', ''

    @classmethod
    def _should_prefer_intro_images(cls, product: Dict) -> bool:
        name = cls._normalize_text(product.get('name', ''))
        model = cls._normalize_text(product.get('model', ''))
        intro = html.unescape(str(product.get('intro', '') or ''))
        first_titles = re.findall(r'title=["\']([^"\']+)["\']', intro, re.I)[:3]
        normalized_titles = [cls._normalize_text(title) for title in first_titles if title]

        if any('参数' in title or '规格' in title or '说明' in title for title in normalized_titles):
            return False

        if normalized_titles and all(re.fullmatch(r'\d+', title) or re.fullmatch(r'\d+jpg', title) for title in normalized_titles):
            return False

        if name and name in cls._normalize_text(intro[:1200]):
            return True
        if model and len(model) >= 3 and model in cls._normalize_text(intro[:1200]):
            return True

        return False

    @classmethod
    def _get_fallback_image_url(cls, product: Dict) -> str:
        local_images = cls.get_product_images(product, max_images=1)
        if cls._should_prefer_intro_images(product) and local_images:
            return cls._normalize_source_url(local_images[0].get('url', ''))
        return ''

    @classmethod
    def convert_to_full_url(cls, url: str) -> str:
        """将相对路径转换为完整URL"""
        if not url:
            return ''

        if url.startswith('http://') or url.startswith('https://'):
            return url

        if url.startswith('../'):
            url = url[3:]
        elif url.startswith('./'):
            url = url[2:]

        return f"{cls.BASE_URL}/{url.lstrip('/')}"

    @classmethod
    def _normalize_source_url(cls, url: str) -> str:
        full_url = cls.convert_to_full_url(url)
        if not full_url:
            return ''
        return full_url.replace(cls.BASE_URL, cls.FILE_BASE_URL, 1)

    @classmethod
    def extract_images(cls, intro: str) -> List[Dict]:
        """从商品intro字段提取图片URL"""
        if not intro:
            return []

        decoded_intro = html.unescape(intro)
        img_pattern = r'<img[^>]+src=["\']([^"\']+)["\'][^>]*(?:title=["\']([^"\']*)["\'])?'
        matches = re.findall(img_pattern, decoded_intro)

        images = []
        for url, title in matches:
            full_url = cls.convert_to_full_url(url)
            images.append({
                'url': full_url,
                'title': title or '',
                'thumb': full_url
            })
        return images

    @classmethod
    def get_product_images(cls, product: Dict, max_images: int = 5) -> List[Dict]:
        """获取商品的所有图片"""
        intro = product.get('intro', '')
        images = cls.extract_images(intro)

        product_images = []
        exclude_keywords = ['温馨提示', '固定格式', '固定模板', '提示']

        for img in images:
            title = img.get('title', '')
            should_exclude = any(keyword in title for keyword in exclude_keywords)
            if not should_exclude:
                product_images.append(img)
            if len(product_images) >= max_images:
                break

        return product_images

    @classmethod
    def get_first_image(cls, product: Dict) -> Optional[str]:
        images = cls.get_product_images(product, max_images=1)
        if images:
            return images[0].get('url')
        return None

    @classmethod
    def build_proxy_url(cls, product: Dict, index: int = 0) -> str:
        product_code = str(product.get('code', '') or '').strip()
        if product_code:
            suffix = f'?index={index}' if index else ''
            return f'/api/product/image-proxy/{product_code}{suffix}'

        product_id = str(product.get('product_id', '') or '').strip()
        if product_id:
            suffix = f'?index={index}' if index else ''
            return f'/api/product/image-proxy/by-id/{product_id}{suffix}'

        return ''

    @classmethod
    def get_proxy_images(cls, product: Dict, max_images: int = 3) -> List[Dict]:
        product_id = str(product.get('product_id', '') or '')
        source_image_url = str(product.get('source_image_url', '') or '').strip()
        images = cls.get_product_images(product, max_images=max_images)

        if images:
            proxy_images = []
            for index, image in enumerate(images[:max_images]):
                proxy_item_url = cls.build_proxy_url(product, index=index)
                normalized_source_url = cls._normalize_source_url(image.get('url', ''))
                proxy_images.append({
                    **image,
                    'thumb': normalized_source_url or proxy_item_url,
                    'source_url': normalized_source_url,
                    'url': proxy_item_url or normalized_source_url,
                    'proxy_url': proxy_item_url,
                    'product_id': product_id
                })
            return proxy_images

        proxy_url = cls.build_proxy_url(product, index=0)
        if proxy_url:
            return [{
                'title': str(product.get('name', '') or ''),
                'thumb': source_image_url or proxy_url,
                'source_url': source_image_url,
                'url': proxy_url,
                'proxy_url': proxy_url,
                'product_id': product_id
            }]

        return []

    @classmethod
    def prepare_product_proxy_images(cls, product: Dict, max_images: int = 1) -> Dict:
        proxy_images = cls.get_proxy_images(product, max_images=max_images)
        product['images'] = proxy_images
        product['image_url'] = proxy_images[0].get('url', '') if proxy_images else ''
        product['source_image_url'] = proxy_images[0].get('source_url', '') if proxy_images else ''
        return product

    @classmethod
    def prepare_products_for_display(cls, products: List[Dict]) -> List[Dict]:
        for product in products:
            cls.prepare_product_proxy_images(product)
        return products

    @classmethod
    def refresh_product_image(cls, product: Dict) -> Dict:
        resolved_image_url = cls.resolve_product_image_url(product)
        product_id = str(product.get('product_id', '') or '')
        proxy_url = cls.build_proxy_url(product, index=0)

        if resolved_image_url:
            product['images'] = [{
                'title': str(product.get('name', '') or ''),
                'thumb': resolved_image_url,
                'source_url': resolved_image_url,
                'url': proxy_url or resolved_image_url,
                'proxy_url': proxy_url,
                'product_id': product_id
            }]
            product['image_url'] = proxy_url or resolved_image_url
            product['source_image_url'] = resolved_image_url
        else:
            cls.prepare_product_proxy_images(product)

        return product

    @classmethod
    def enrich_products_with_resolved_images(cls, products: List[Dict]) -> List[Dict]:
        for product in products:
            cls.refresh_product_image(product)
        return products

    @classmethod
    def enrich_products_with_images(cls, products: List[Dict]) -> List[Dict]:
        return cls.prepare_products_for_display(products)

    @classmethod
    def resolve_product_image_url(cls, product: Dict) -> str:
        cache_key = cls._get_cache_key(product)
        if cache_key in cls._resolved_image_cache:
            return cls._resolved_image_cache[cache_key]

        image_url, product_id = cls._resolve_from_search(product)
        if product_id:
            product['product_id'] = product_id
            cls._product_id_cache[cache_key] = product_id
        if image_url:
            cls._resolved_image_cache[cache_key] = image_url
            return image_url

        fallback_url = cls._get_fallback_image_url(product)
        cls._resolved_image_cache[cache_key] = fallback_url
        return fallback_url

    @classmethod
    def resolve_image_response(cls, product: Dict, index: int = 0):
        target_url = ''

        if index == 0:
            target_url = cls.resolve_product_image_url(product)
        else:
            images = cls.get_product_images(product, max_images=index + 1)
            if index < len(images):
                target_url = cls._normalize_source_url(images[index].get('url', ''))

        if not target_url:
            return None, ''

        response = cls._request_safe(target_url, stream=True)
        if cls._looks_like_image_response(response):
            return response, target_url

        if response is not None:
            response.close()

        if index != 0:
            fallback_url = cls.resolve_product_image_url(product)
            if fallback_url and fallback_url != target_url:
                fallback_response = cls._request_safe(fallback_url, stream=True)
                if cls._looks_like_image_response(fallback_response):
                    return fallback_response, fallback_url
                if fallback_response is not None:
                    fallback_response.close()

        return None, ''

    @classmethod
    def find_product_by_code(cls, products: List[Dict], product_code: str) -> Optional[Dict]:
        product_code = str(product_code or '').strip()
        if not product_code:
            return None
        for product in products or []:
            if str(product.get('code', '') or '').strip() == product_code:
                return product
        return None

    @classmethod
    def find_product_by_id(cls, products: List[Dict], product_id: str) -> Optional[Dict]:
        product_id = str(product_id or '').strip()
        if not product_id:
            return None
        for product in products or []:
            cls.ensure_product_metadata(product)
            if str(product.get('product_id', '') or '').strip() == product_id:
                return product
        return None

    @classmethod
    def get_image_api_payload(cls, product: Dict) -> Dict:
        product = cls.ensure_product_metadata(product)
        images = cls.get_proxy_images(product)
        return {
            'success': True,
            'image_url': images[0].get('url') if images else '',
            'source_image_url': images[0].get('source_url') if images else '',
            'images': images,
            'product_id': str(product.get('product_id', '') or '')
        }

    @classmethod
    def get_placeholder_svg(cls) -> bytes:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">'
            '<rect fill="#f1f5f9" width="120" height="120"/>'
            '<text x="60" y="66" text-anchor="middle" fill="#94a3b8" font-size="14">暂无图片</text>'
            '</svg>'
        ).encode('utf-8')


def get_image_url_from_product(product: Dict) -> str:
    """快捷函数：获取商品图片URL"""
    return ProductImageHandler.get_first_image(product) or ''


def get_product_images(product: Dict) -> List[Dict]:
    """快捷函数：获取商品图片列表"""
    return ProductImageHandler.get_product_images(product)
