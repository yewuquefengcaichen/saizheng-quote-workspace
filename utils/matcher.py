# -*- coding: utf-8 -*-
"""
智能匹配引擎
功能：精准匹配 + 模糊匹配 + 同义词扩展 + 历史反馈学习
"""

import re
import math
import html
from difflib import SequenceMatcher
from typing import List, Dict, Any, Optional, Callable
import jieba
import jieba.analyse

from utils.normalizer import normalize_quote_item


PRODUCT_CODE_FIELDS = ['code', 'product_code', 'item_code', 'sku', '编号', '编码']


def clean_nan(obj):
    """清理对象中的NaN值，使其可以被JSON序列化"""
    if isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_nan(item) for item in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if obj is None:
        return None
    return obj


def get_product_code(product: Dict[str, Any]) -> str:
    for field in PRODUCT_CODE_FIELDS:
        value = product.get(field)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ''


def product_has_image(product: Dict[str, Any]) -> bool:
    if not product:
        return False
    if product.get('image_url'):
        return True
    return bool(product.get('images') or [])


def build_query_signature(item: Dict[str, Any]) -> str:
    normalized = normalize_quote_item(item or {})
    return '||'.join([
        str(normalized.get('normalized_name', '')).strip().lower(),
        str(normalized.get('normalized_spec', '')).strip().lower(),
        str(normalized.get('normalized_unit', '')).strip().lower()
    ])


def build_mapping_signature(item: Dict[str, Any]) -> str:
    normalized = normalize_quote_item(item or {})
    parts = [
        str(normalized.get('source_type', '')).strip().lower(),
        str(normalized.get('normalized_name', '')).strip().lower(),
        str(normalized.get('normalized_spec', '')).strip().lower(),
        str(normalized.get('normalized_unit', '')).strip().lower(),
        str(normalized.get('remark', '') or '').strip().lower()
    ]
    return '||'.join(parts)


def prepare_query_item(item: Dict[str, Any]) -> Dict[str, Any]:
    prepared = normalize_quote_item(item or {})
    prepared['query_signature'] = build_query_signature(prepared)
    prepared['mapping_signature'] = build_mapping_signature(prepared)
    return prepared


def compute_query_similarity(item_a: Dict[str, Any], item_b: Dict[str, Any]) -> float:
    a = normalize_quote_item(item_a or {})
    b = normalize_quote_item(item_b or {})
    text_a = ' '.join(
        str(part).strip() for part in [a.get('normalized_name', ''), a.get('normalized_spec', ''), a.get('normalized_unit', '')]
        if str(part).strip()
    )
    text_b = ' '.join(
        str(part).strip() for part in [b.get('normalized_name', ''), b.get('normalized_spec', ''), b.get('normalized_unit', '')]
        if str(part).strip()
    )
    if not text_a or not text_b:
        return 0.0
    return SequenceMatcher(None, text_a, text_b).ratio()


def _merge_feedback_rows(rows_a: List[Dict[str, Any]], rows_b: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged = []
    seen = set()
    for row in (rows_a or []) + (rows_b or []):
        row_id = row.get('id')
        row_key = row_id if row_id is not None else (
            row.get('query_signature', ''),
            row.get('action', ''),
            row.get('selected_product_code', ''),
            row.get('top_candidate_code', ''),
            row.get('created_at', '')
        )
        if row_key in seen:
            continue
        seen.add(row_key)
        merged.append(dict(row))
    return merged


def collect_feedback_summary(feedback_rows: List[Dict[str, Any]], query_item: Dict[str, Any]) -> Dict[str, Any]:
    selected_counts = {}
    selected_image_counts = {}
    rejected_top_codes = {}
    no_match_count = 0.0
    ask_boss_count = 0.0
    template_hit_count = 0.0
    mapping_changed_count = 0.0
    prepared = prepare_query_item(query_item)

    for row in feedback_rows or []:
        row_item = {
            'name': row.get('original_name', ''),
            'spec': row.get('original_spec', ''),
            'unit': row.get('original_unit', ''),
            'normalized_name': row.get('normalized_name', ''),
            'normalized_spec': row.get('normalized_spec', ''),
            'normalized_unit': row.get('normalized_unit', ''),
            'source_type': row.get('source_type', '')
        }
        similarity = compute_query_similarity(prepared, row_item)
        if similarity >= 0.985:
            similarity_weight = 1.0
        elif similarity >= 0.94:
            similarity_weight = 0.8
        elif similarity >= 0.85:
            similarity_weight = 0.5
        else:
            similarity_weight = 0.0

        mapping_bonus = 0.25 if row.get('mapping_signature') and row.get('mapping_signature') == prepared.get('mapping_signature') else 0.0
        stored_weight = float(row.get('feedback_weight') or 1)
        weight = (similarity_weight + mapping_bonus) * stored_weight

        if weight <= 0:
            continue

        if row.get('template_hit'):
            template_hit_count += weight
        if row.get('mapping_changed'):
            mapping_changed_count += weight

        action = row.get('action', '')
        selected_code = str(row.get('selected_product_code') or '').strip()
        top_code = str(row.get('top_candidate_code') or '').strip()

        if action == 'select' and selected_code:
            selected_counts[selected_code] = selected_counts.get(selected_code, 0.0) + weight
            if row.get('with_product_image'):
                selected_image_counts[selected_code] = selected_image_counts.get(selected_code, 0.0) + weight
        elif action == 'no_match':
            no_match_count += weight
            if top_code:
                rejected_top_codes[top_code] = rejected_top_codes.get(top_code, 0.0) + weight
        elif action == 'ask_boss':
            ask_boss_count += weight
            if top_code:
                rejected_top_codes[top_code] = rejected_top_codes.get(top_code, 0.0) + (weight * 0.5)

    return {
        'selected_counts': selected_counts,
        'selected_image_counts': selected_image_counts,
        'rejected_top_codes': rejected_top_codes,
        'no_match_count': round(no_match_count, 2),
        'ask_boss_count': round(ask_boss_count, 2),
        'template_hit_count': round(template_hit_count, 2),
        'mapping_changed_count': round(mapping_changed_count, 2),
        'feedback_count': len(feedback_rows or []),
        'query_signature': prepared.get('query_signature', ''),
        'mapping_signature': prepared.get('mapping_signature', '')
    }


def apply_learning_to_match(match: Dict[str, Any], feedback_summary: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    product = match.get('product') or {}
    product_code = get_product_code(product)
    feedback_summary = feedback_summary or {}

    selected_counts = feedback_summary.get('selected_counts', {})
    selected_image_counts = feedback_summary.get('selected_image_counts', {})
    rejected_top_codes = feedback_summary.get('rejected_top_codes', {})
    template_hit_count = float(feedback_summary.get('template_hit_count', 0) or 0)
    mapping_changed_count = float(feedback_summary.get('mapping_changed_count', 0) or 0)

    selection_boost = min(float(selected_counts.get(product_code, 0.0)) * 0.08, 0.28) if product_code else 0.0
    image_bonus = min(float(selected_image_counts.get(product_code, 0.0)) * 0.03, 0.08) if product_code else 0.0
    if product_has_image(product):
        image_bonus += 0.015
    template_bonus = min(template_hit_count * 0.008, 0.04)
    mapping_penalty = min(mapping_changed_count * 0.01, 0.05)
    rejection_penalty = min(float(rejected_top_codes.get(product_code, 0.0)) * 0.06, 0.18) if product_code else 0.0

    boosted_score = max(
        0.0,
        min(1.0, float(match.get('score') or 0) + selection_boost + image_bonus + template_bonus - rejection_penalty - mapping_penalty)
    )
    updated = dict(match)
    updated['base_score'] = round(float(match.get('score') or 0), 3)
    updated['score'] = round(boosted_score, 3)
    updated['learning_details'] = {
        'selection_boost': round(selection_boost, 3),
        'image_bonus': round(image_bonus, 3),
        'template_bonus': round(template_bonus, 3),
        'mapping_penalty': round(mapping_penalty, 3),
        'rejection_penalty': round(rejection_penalty, 3),
        'feedback_count': int(feedback_summary.get('feedback_count', 0) or 0)
    }
    updated['feedback_summary'] = {
        'feedback_count': int(feedback_summary.get('feedback_count', 0) or 0),
        'no_match_count': round(float(feedback_summary.get('no_match_count', 0) or 0), 2),
        'ask_boss_count': round(float(feedback_summary.get('ask_boss_count', 0) or 0), 2),
        'template_hit_count': round(float(feedback_summary.get('template_hit_count', 0) or 0), 2),
        'mapping_changed_count': round(float(feedback_summary.get('mapping_changed_count', 0) or 0), 2)
    }
    return updated


def annotate_candidate_reason(match: Dict[str, Any]) -> Dict[str, Any]:
    updated = dict(match)
    product = updated.get('product') or {}
    updated['has_image'] = product_has_image(product)
    updated['product_code'] = get_product_code(product)

    details = updated.get('learning_details') or {}
    reasons = []
    if float(details.get('selection_boost') or 0) > 0:
        reasons.append('历史确认')
    if float(details.get('image_bonus') or 0) > 0.02:
        reasons.append('图片辅助')
    if float(details.get('template_bonus') or 0) > 0:
        reasons.append('模板经验')
    if float(details.get('rejection_penalty') or 0) > 0:
        reasons.append('曾被排除')
    if float(details.get('mapping_penalty') or 0) > 0:
        reasons.append('人工修正痕迹')
    if reasons:
        updated['learning_reason'] = ' / '.join(reasons)
    return updated


def finalize_matches(matches: List[Dict[str, Any]], feedback_summary: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    finalized = [apply_learning_to_match(match, feedback_summary) for match in (matches or [])]
    finalized.sort(key=lambda item: (item.get('score', 0), item.get('base_score', 0)), reverse=True)

    if len(finalized) >= 2:
        reordered = [finalized[0]]
        for match in finalized[1:]:
            prev = reordered[-1]
            score_diff = abs(float(prev.get('score') or 0) - float(match.get('score') or 0))
            if score_diff <= 0.03 and product_has_image(match.get('product') or {}) and not product_has_image(prev.get('product') or {}):
                reordered[-1] = match
                reordered.append(prev)
            else:
                reordered.append(match)
        finalized = reordered

    return [annotate_candidate_reason(match) for match in finalized]


def get_feedback_hint(feedback_summary: Optional[Dict[str, Any]]) -> str:
    feedback_summary = feedback_summary or {}
    feedback_count = int(feedback_summary.get('feedback_count', 0) or 0)
    if feedback_count <= 0:
        return ''

    parts = [f'已参考{feedback_count}条历史反馈']
    template_hit_count = float(feedback_summary.get('template_hit_count', 0) or 0)
    if template_hit_count >= 1:
        parts.append('含模板命中经验')
    mapping_changed_count = float(feedback_summary.get('mapping_changed_count', 0) or 0)
    if mapping_changed_count >= 1:
        parts.append('已识别人工修正痕迹')
    return '，'.join(parts)


def get_match_feedback_payload(
    query_item: Dict[str, Any],
    result_row: Dict[str, Any],
    selected_product: Optional[Dict[str, Any]],
    action: str,
    source_type: str = '',
    template_name: str = '',
    template_hit: bool = False
) -> Dict[str, Any]:
    prepared = prepare_query_item(query_item)
    matches = result_row.get('matches') or []
    top_candidate = matches[0] if matches else None
    top_product = (top_candidate or {}).get('product') or {}

    if isinstance(selected_product, dict) and selected_product.get('product'):
        selected_product_obj = selected_product.get('product') or {}
    else:
        selected_product_obj = selected_product or {}

    selected_code = get_product_code(selected_product_obj)
    top_code = get_product_code(top_product)

    selected_rank = 0
    selected_score = 0.0
    if action == 'select' and isinstance(selected_product, dict):
        selected_index = selected_product.get('index')
        selected_score = float(selected_product.get('score') or 0)
        for rank, match in enumerate(matches, start=1):
            if match.get('index') == selected_index:
                selected_rank = rank
                if not selected_score:
                    selected_score = float(match.get('score') or 0)
                break

    top_candidate_score = float((top_candidate or {}).get('score') or 0)
    feedback_weight = 1.0
    if action == 'select' and selected_rank > 0:
        feedback_weight += max(0, 4 - selected_rank) * 0.12
    elif action == 'no_match' and top_candidate_score >= 0.55:
        feedback_weight = 1.15
    elif action == 'ask_boss':
        feedback_weight = 0.75

    return {
        'source_type': source_type,
        'template_name': template_name,
        'template_hit': template_hit,
        'action': action,
        'original_name': str(query_item.get('name', '') or ''),
        'original_spec': str(query_item.get('spec', '') or ''),
        'original_unit': str(query_item.get('unit', '') or ''),
        'normalized_name': str(prepared.get('normalized_name', '') or ''),
        'normalized_spec': str(prepared.get('normalized_spec', '') or ''),
        'normalized_unit': str(prepared.get('normalized_unit', '') or ''),
        'selected_product_code': selected_code,
        'selected_product_name': str(selected_product_obj.get('name', '') or ''),
        'top_candidate_code': top_code,
        'top_candidate_name': str(top_product.get('name', '') or ''),
        'top_candidate_score': top_candidate_score,
        'top_candidate_rank': 1 if top_candidate else 0,
        'selected_rank': selected_rank,
        'selected_score': float(selected_score or 0),
        'with_product_image': product_has_image(selected_product_obj),
        'ocr_confidence': float(query_item.get('ocr_confidence') or query_item.get('confidence') or 0),
        'query_signature': prepared.get('query_signature', ''),
        'mapping_signature': prepared.get('mapping_signature', ''),
        'mapping_changed': bool(query_item.get('mapping_changed')),
        'feedback_weight': round(feedback_weight, 2)
    }


class ProductMatcher:
    """商品匹配器"""

    def __init__(self, products: List[Dict]):
        self.products = products or []
        self.synonyms = {}

        jieba.initialize()
        self._build_index()

    def _build_index(self):
        """建立商品索引"""
        self.product_search_data = []

        for product in self.products:
            product_name = str(product.get('name', '') or '')
            product_spec_source = self._prepare_product_spec_text(product)
            normalized_product_name = normalize_quote_item({'name': product_name}).get('normalized_name', '')
            normalized_product_spec = normalize_quote_item({'spec': product_spec_source}).get('normalized_spec', '')
            product_compare_name = normalized_product_name or product_name
            product_text = f"{product_compare_name} {normalized_product_spec}".strip()
            product_keywords = self._extract_keywords(product_text or product_name)
            product_gbs = re.findall(r'GB\s*[-/]?\s*(\d+(?:[-/]\d+)*)', product_text, flags=re.IGNORECASE)

            self.product_search_data.append({
                'name': product_name,
                'compare_name': product_compare_name,
                'compare_text': product_text,
                'keywords': product_keywords,
                'gbs': product_gbs
            })

    def _get_product_search_data(self, idx: int, product: Dict[str, Any]) -> Dict[str, Any]:
        if idx < len(self.product_search_data):
            return self.product_search_data[idx]

        product_name = str(product.get('name', '') or '')
        compare_text = self._prepare_product_spec_text(product) or product_name
        return {
            'name': product_name,
            'compare_name': product_name,
            'compare_text': compare_text,
            'keywords': self._extract_keywords(compare_text or product_name),
            'gbs': re.findall(r'GB\s*[-/]?\s*(\d+(?:[-/]\d+)*)', compare_text, flags=re.IGNORECASE)
        }

    def _prepare_product_spec_text(self, product: Dict[str, Any]) -> str:
        """提取适合匹配的商品规格文本，避免把整段 HTML 详情直接参与相似度计算"""
        spec_source = product.get('model') or product.get('spec') or product.get('intro') or ''
        text = html.unescape(str(spec_source))
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'(?:https?://|www\.|\.\./)\S+', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:120]

    def _extract_keywords(self, text: str) -> set:
        """提取关键词"""
        if not text:
            return set()

        keywords = set()
        for word in jieba.cut(text):
            word = word.strip()
            if len(word) >= 2:
                keywords.add(word)
        return keywords

    def _normalize_category_text(self, text: str) -> str:
        value = str(text or '').lower()
        for separator in ['ξ', '|', '/', '\\', '＞', '>']:
            value = value.replace(separator, ' ')
        return re.sub(r'\s+', '', value)

    def update_synonyms(self, synonyms: Dict[str, List[str]]):
        """更新同义词库"""
        self.synonyms = synonyms or {}

    def _expand_with_synonyms(self, keywords: set) -> set:
        """使用同义词扩展关键词"""
        expanded = set(keywords)
        for word in list(keywords):
            for main_word, synonym_list in (self.synonyms or {}).items():
                if word == main_word or word in synonym_list:
                    expanded.add(main_word)
                    expanded.update(synonym_list)
        return expanded

    def _calculate_similarity(self, text1: str, text2: str, keywords1: Optional[set] = None, keywords2: Optional[set] = None) -> float:
        """计算两个文本的相似度"""
        if not text1 or not text2:
            return 0.0

        ratio1 = SequenceMatcher(None, text1, text2).ratio()
        kw1 = keywords1 if keywords1 is not None else self._extract_keywords(text1)
        kw2 = keywords2 if keywords2 is not None else self._extract_keywords(text2)

        if not kw1 or not kw2:
            return ratio1 * 0.5

        intersection = kw1 & kw2
        union = kw1 | kw2
        jaccard = len(intersection) / len(union) if union else 0

        contains_score = 0.0
        if text1 in text2 or text2 in text1:
            contains_score = 0.8

        final_score = max(
            ratio1 * 0.3 + jaccard * 0.5 + contains_score * 0.2,
            ratio1,
            jaccard,
            contains_score
        )
        return min(final_score, 1.0)

    def _match_product_type(self, query: str, product_name: str) -> float:
        """匹配产品类型"""
        product_types = {
            '手套': ['手套', '防护手套', '劳保手套', '工作手套'],
            '布手套': ['布手套', '棉手套', '线手套', '纱手套'],
            '纱手套': ['纱手套', '线手套', '棉纱手套', '布手套'],
            '线手套': ['线手套', '纱手套', '棉线手套'],
            '袖套': ['袖套', '套袖', '手袖', '护袖'],
            '套袖': ['袖套', '套袖', '手袖', '护袖'],
            '手袖': ['袖套', '套袖', '手袖', '护袖'],
            '安全帽': ['安全帽', '防护帽', '头盔', '帽'],
            '口罩': ['口罩', '防尘口罩', '防护口罩', 'KN95'],
            '防尘口罩': ['防尘口罩', '口罩', 'KN95', '防护口罩'],
            '劳保鞋': ['劳保鞋', '安全鞋', '防护鞋', '工作鞋'],
            '安全鞋': ['安全鞋', '劳保鞋', '防护鞋'],
            '雨衣': ['雨衣', '雨披', '防雨服', '套装雨衣'],
            '雨鞋': ['雨鞋', '雨靴', '胶鞋', '水鞋'],
            '水鞋': ['水鞋', '雨鞋', '雨靴', '胶鞋'],
            '绝缘手套': ['绝缘手套', '电工手套', '高压手套'],
            '绝缘鞋': ['绝缘鞋', '电工鞋', '高压鞋'],
            '耳塞': ['耳塞', '隔音耳塞', '防护耳塞'],
            '眼镜': ['眼镜', '防护眼镜', '护目镜', '防风眼镜'],
            '防风眼镜': ['防风眼镜', '防护眼镜', '护目镜', '眼镜'],
            '电焊手套': ['电焊手套', '焊工手套', '焊接手套'],
            '滤毒盒': ['滤毒盒', '滤盒', '防毒滤盒'],
            '防毒面具': ['防毒面具', '呼吸防护', '半面罩'],
            '毛巾': ['毛巾', '面巾', '手巾'],
            '洗衣粉': ['洗衣粉', '洗衣液', '洗涤剂'],
            '反光衣': ['反光衣', '反光背心', '警示衣'],
            '救生衣': ['救生衣', '救生服', '漂浮衣'],
            '解放鞋': ['解放鞋', '帆布鞋', '工作鞋'],
            '面罩': ['面罩', '防护面罩', '面屏'],
        }

        query_lower = (query or '').lower()
        name_lower = (product_name or '').lower()

        for ptype, aliases in product_types.items():
            if ptype in query_lower:
                for alias in aliases:
                    if alias in name_lower:
                        return 0.9
        return 0.0

    def _match_brand(self, query_brand: str, product_brand: str, product_name: str) -> float:
        """品牌匹配评分"""
        if not query_brand:
            return 0.0

        query_brand = query_brand.lower().strip()
        product_brand = (product_brand or '').lower().strip()
        product_name = (product_name or '').lower()

        brand_aliases = {
            '赛正': ['赛正', 'sz', 'saizheng'],
            '星宇': ['星宇', 'xy', 'xingyu'],
            '登升': ['登升', 'ds', 'dengsheng'],
            '3m': ['3m', '3m公司'],
            '霍尼韦尔': ['霍尼韦尔', 'honeywell', 'honey well'],
            '安尔康': ['安尔康', 'aek', 'anerkang'],
            '稳健': ['稳健', 'wj', 'wenjian'],
            '朝美': ['朝美', 'cm', 'chaomei'],
            '海固': ['海固', 'hg', 'haigu'],
            '华信': ['华信', 'hx', 'huaxin'],
            '盾牌': ['盾牌', 'dp', 'dunpai'],
            '邦维': ['邦维', 'bw', 'bangwei'],
            '可孚': ['可孚', 'kf', 'kefu'],
            '绿盾': ['绿盾', 'ld', 'lvdun'],
        }

        query_aliases = [query_brand]
        for main_brand, aliases in brand_aliases.items():
            alias_values = [a.lower() for a in aliases]
            if query_brand == main_brand or query_brand in alias_values:
                query_aliases = [main_brand.lower()] + alias_values
                break

        for alias in query_aliases:
            if alias == product_brand or alias in product_brand:
                return 1.0
            if alias in product_name:
                return 0.8
        return 0.0

    def _extract_brand_from_name(self, name: str) -> str:
        """从产品名称中提取品牌"""
        if not name:
            return ''

        brand_keywords = [
            '赛正', '星宇', '登升', '3M', '霍尼韦尔', '安尔康', '邦维',
            '海固', '华信', '盾牌', '稳健', '朝美', '可孚', '绿盾',
            '南极人', '德尔格', '梅思安', '代尔塔', '优唯斯', '洁适'
        ]

        name_lower = name.lower()
        for brand in brand_keywords:
            if brand.lower() in name_lower:
                return brand

        match = re.match(r'^([A-Z]{2,3})\d*', name)
        if match:
            code = match.group(1).upper()
            code_to_brand = {
                'SZ': '赛正',
                'XY': '星宇',
                'DS': '登升',
                'AEK': '安尔康',
                'HG': '海固',
            }
            if code in code_to_brand:
                return code_to_brand[code]

        return ''

    def _fetch_feedback_rows(self, query_item: Dict[str, Any], feedback_provider: Optional[Callable[..., List[Dict[str, Any]]]]) -> List[Dict[str, Any]]:
        if not callable(feedback_provider):
            return []

        prepared = prepare_query_item(query_item)
        signature_rows = feedback_provider(query_signature=prepared.get('query_signature', '')) or []
        normalized_rows = feedback_provider(
            normalized_name=prepared.get('normalized_name', ''),
            normalized_spec=prepared.get('normalized_spec', ''),
            normalized_unit=prepared.get('normalized_unit', '')
        ) or []
        mapping_rows = feedback_provider(mapping_signature=prepared.get('mapping_signature', '')) or []
        return _merge_feedback_rows(_merge_feedback_rows(signature_rows, normalized_rows), mapping_rows)

    def get_feedback_summary(self, query_item: Dict[str, Any], feedback_provider: Optional[Callable[..., List[Dict[str, Any]]]] = None) -> Dict[str, Any]:
        rows = self._fetch_feedback_rows(query_item, feedback_provider)
        return collect_feedback_summary(rows, query_item)

    def match_single(
        self,
        query_item: Dict,
        synonyms: Dict = None,
        feedback_provider: Optional[Callable[..., List[Dict[str, Any]]]] = None
    ) -> List[Dict]:
        """匹配单个报价项"""
        if synonyms:
            self.synonyms = synonyms

        prepared_query = prepare_query_item(query_item)
        query_name = prepared_query.get('normalized_name') or prepared_query.get('name', '')
        query_spec = prepared_query.get('normalized_spec') or prepared_query.get('spec', '')
        query_brand = prepared_query.get('brand', '')
        query_text = f"{query_name} {query_spec}".strip()

        if not query_name:
            return []

        base_query_keywords = self._extract_keywords(query_text)
        query_keywords = self._expand_with_synonyms(base_query_keywords)
        extracted_brand = self._extract_brand_from_name(query_name)
        spec_keywords = self._extract_keywords(query_spec) if query_spec else set()
        query_gbs = re.findall(r'GB\s*[-/]?\s*(\d+(?:[-/]\d+)*)', query_spec, flags=re.IGNORECASE) if query_spec else []
        normalized_query_gbs = [gb.replace('/', '-') for gb in query_gbs]

        results = []
        for idx, product in enumerate(self.products):
            product_name = product.get('name', '')
            product_brand = product.get('brand', '')
            if not product_name:
                continue

            product_data = self._get_product_search_data(idx, product)
            product_compare_name = product_data.get('compare_name') or product_name
            product_text = product_data.get('compare_text') or product_name
            product_keywords = product_data.get('keywords') or self._extract_keywords(product_text)
            product_gbs = [gb.replace('/', '-') for gb in (product_data.get('gbs') or [])]

            similarity = self._calculate_similarity(query_text, product_text or product_name, keywords1=base_query_keywords, keywords2=product_keywords)
            type_score = self._match_product_type(query_name, product_compare_name or product_name)
            keyword_overlap = len(query_keywords & product_keywords) / max(len(query_keywords), 1)

            spec_score = 0.0
            if query_spec:
                if normalized_query_gbs and product_gbs and any(gb in product_gbs for gb in normalized_query_gbs):
                    spec_score += 0.3
                if spec_keywords:
                    spec_overlap = len(spec_keywords & product_keywords) / max(len(spec_keywords), 1)
                    spec_score += spec_overlap * 0.2

            brand_score = self._match_brand(query_brand or extracted_brand, product_brand, product_name)
            final_score = (
                similarity * 0.30 +
                type_score * 0.20 +
                keyword_overlap * 0.20 +
                spec_score * 0.10 +
                brand_score * 0.20
            )

            if final_score >= 0.15:
                results.append({
                    'index': idx,
                    'product': product,
                    'score': round(final_score, 3),
                    'match_type': 'exact' if final_score >= 0.7 else 'fuzzy',
                    'brand_matched': brand_score > 0.5,
                    'score_details': {
                        'similarity': round(similarity, 3),
                        'type_match': round(type_score, 3),
                        'keyword_overlap': round(keyword_overlap, 3),
                        'spec_match': round(spec_score, 3),
                        'brand_match': round(brand_score, 3)
                    }
                })

        results.sort(key=lambda item: item['score'], reverse=True)
        results = results[:20]

        feedback_summary = self.get_feedback_summary(prepared_query, feedback_provider)
        results = finalize_matches(results, feedback_summary)
        return clean_nan(results)

    def match_all(
        self,
        query_items: List[Dict],
        synonyms: Dict = None,
        feedback_provider: Optional[Callable[..., List[Dict[str, Any]]]] = None
    ) -> List[Dict]:
        """批量匹配所有报价项"""
        results = []

        for idx, item in enumerate(query_items or []):
            prepared_item = prepare_query_item(item)
            matches = self.match_single(prepared_item, synonyms, feedback_provider=feedback_provider)
            feedback_summary = self.get_feedback_summary(prepared_item, feedback_provider)
            best_match = matches[0] if matches else None

            alternatives = []
            if not matches or (best_match and best_match['score'] < 0.4):
                alternatives = self.find_alternatives(prepared_item, limit=5)

            auto_threshold = 0.45 if int(feedback_summary.get('feedback_count', 0) or 0) >= 3 else 0.5
            auto_action = None
            auto_selected = None
            if best_match and best_match['score'] >= auto_threshold:
                auto_action = 'select'
                auto_selected = best_match

            result = {
                'index': idx,
                'query_item': prepared_item,
                'matches': matches,
                'best_match': best_match,
                'alternatives': alternatives,
                'confirmed': False,
                'action': auto_action,
                'selected_product': auto_selected,
                'feedback_hint': get_feedback_hint(feedback_summary),
                'feedback_summary': {
                    'feedback_count': int(feedback_summary.get('feedback_count', 0) or 0),
                    'no_match_count': round(float(feedback_summary.get('no_match_count', 0) or 0), 2),
                    'ask_boss_count': round(float(feedback_summary.get('ask_boss_count', 0) or 0), 2),
                    'template_hit_count': round(float(feedback_summary.get('template_hit_count', 0) or 0), 2),
                    'mapping_changed_count': round(float(feedback_summary.get('mapping_changed_count', 0) or 0), 2)
                },
                'source_type': prepared_item.get('source_type', ''),
                'query_signature': prepared_item.get('query_signature', ''),
                'image_assisted': any(product_has_image((match.get('product') or {})) for match in matches[:3])
            }
            results.append(result)

        return clean_nan(results)

    def search_by_keyword(self, keyword: str, limit: int = 50) -> List[Dict]:
        """关键词搜索商品"""
        results = []
        keyword_lower = (keyword or '').lower()

        for idx, product in enumerate(self.products):
            product_name = product.get('name', '').lower()
            if keyword_lower in product_name:
                results.append({
                    'index': idx,
                    'product': product,
                    'score': 1.0
                })

        existing_indexes = {r['index'] for r in results}
        for idx, product in enumerate(self.products):
            if idx in existing_indexes:
                continue
            product_name = product.get('name', '')
            similarity = self._calculate_similarity(keyword, product_name)
            if similarity >= 0.3:
                results.append({
                    'index': idx,
                    'product': product,
                    'score': similarity
                })

        results.sort(key=lambda item: item['score'], reverse=True)
        return clean_nan(results[:limit])

    def find_alternatives(self, query_item: Dict, limit: int = 5) -> List[Dict]:
        """查找替代品推荐（当无匹配或匹配度低时）"""
        prepared_query = prepare_query_item(query_item)
        query_name = prepared_query.get('normalized_name') or prepared_query.get('name', '')
        query_keywords = self._extract_keywords(query_name)

        category_hints = {
            '手套': ['劳保用品|手部防护|手套', '手套'],
            '安全帽': ['劳保用品|头部防护', '安全帽', '头盔'],
            '口罩': ['劳保用品|呼吸防护', '口罩', '防尘'],
            '劳保鞋': ['劳保用品|足部防护', '安全鞋', '劳保鞋'],
            '安全鞋': ['劳保用品|足部防护', '安全鞋', '劳保鞋'],
            '雨衣': ['劳保用品|防护服', '雨衣', '雨披'],
            '雨鞋': ['劳保用品|足部防护', '雨鞋', '雨靴'],
            '眼镜': ['劳保用品|眼面防护', '眼镜', '护目'],
            '耳塞': ['劳保用品|听力防护', '耳塞'],
            '反光衣': ['劳保用品|警示防护', '反光', '警示'],
        }

        target_categories = []
        for hint, categories in category_hints.items():
            if hint in query_name:
                target_categories.extend(categories)

        alternatives = []
        seen_indices = set()

        if target_categories:
            for idx, product in enumerate(self.products):
                if idx in seen_indices:
                    continue
                product_category = product.get('category', '')
                product_name = product.get('name', '')
                normalized_product_category = self._normalize_category_text(product_category)
                normalized_product_name = self._normalize_category_text(product_name)
                for cat in target_categories:
                    normalized_cat = self._normalize_category_text(cat)
                    if normalized_cat and (
                        normalized_cat in normalized_product_category or
                        normalized_cat in normalized_product_name
                    ):
                        similarity = self._calculate_similarity(query_name, product_name)
                        if similarity >= 0.2:
                            alternatives.append({
                                'index': idx,
                                'product': product,
                                'score': round(similarity + (0.01 if product_has_image(product) else 0), 3),
                                'reason': '同类商品',
                                'has_image': product_has_image(product)
                            })
                            seen_indices.add(idx)
                            break

        if len(alternatives) < limit:
            for idx, product in enumerate(self.products):
                if idx in seen_indices:
                    continue
                product_name = product.get('name', '')
                product_data = self._get_product_search_data(idx, product)
                product_compare_name = product_data.get('compare_name') or product_name
                product_keywords = product_data.get('keywords') or self._extract_keywords(product_compare_name)
                overlap = len(query_keywords & product_keywords)
                if overlap >= 2:
                    similarity = self._calculate_similarity(query_name, product_compare_name, keywords1=query_keywords, keywords2=product_keywords)
                    alternatives.append({
                        'index': idx,
                        'product': product,
                        'score': round(similarity + (0.01 if product_has_image(product) else 0), 3),
                        'reason': '关键词相似',
                        'has_image': product_has_image(product)
                    })
                    seen_indices.add(idx)
                if len(alternatives) >= limit * 2:
                    break

        alternatives.sort(key=lambda item: item['score'], reverse=True)
        return clean_nan(alternatives[:limit])

    def find_supplier_variants(self, product_name: str, limit: int = 5) -> List[Dict]:
        """查找同一产品的不同供应商价格对比"""
        if not product_name:
            return []

        core_name = self._extract_core_name(product_name)
        core_keywords = self._extract_keywords(core_name)
        variants = []
        seen_suppliers = set()

        for idx, product in enumerate(self.products):
            p_name = product.get('name', '')
            p_supplier = product.get('supplier', '')
            if not p_name:
                continue

            p_core = self._extract_core_name(p_name)
            p_keywords = self._extract_keywords(p_core)
            if not core_keywords or not p_keywords:
                continue

            overlap = len(core_keywords & p_keywords)
            if overlap < len(core_keywords) * 0.6:
                continue
            if p_supplier in seen_suppliers:
                continue

            similarity = self._calculate_similarity(product_name, p_name)
            if similarity >= 0.5:
                variants.append({
                    'index': idx,
                    'product': product,
                    'similarity': similarity,
                    'supplier': p_supplier or '未知供应商'
                })
                seen_suppliers.add(p_supplier)

            if len(variants) >= limit:
                break

        def get_sort_price(item):
            product = item['product']
            cost = product.get('cost_price')
            if cost and cost > 0:
                return cost
            market = product.get('market_price')
            if market and market > 0:
                return market
            return float('inf')

        variants.sort(key=get_sort_price)
        return clean_nan(variants)

    def _extract_core_name(self, name: str) -> str:
        """提取产品核心名称（去除品牌、规格等修饰）"""
        if not name:
            return ''

        brands = ['星宇', '登升', '南极人', '3M', '霍尼韦尔', '安尔康', '邦维',
                  '海固', '华信', '盾牌', '稳健', '朝美', '可孚', '绿盾']

        core = name
        for brand in brands:
            core = core.replace(brand, '')

        core = re.sub(r'[\d]+只装|[\d]+个装|[\d]+双|[\d]+件|[\d]+ml|[\d]+L|[\d]+g|[\d]+kg', '', core)
        core = re.sub(r'大号|中号|小号|加大|加厚|加绒|加棉', '', core)
        return core.strip()
