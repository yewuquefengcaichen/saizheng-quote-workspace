# -*- coding: utf-8 -*-
"""
报价项标准化工具
功能：统一名称、单位、规格写法，供解析、匹配与反馈学习复用
"""

import json
import os
import re
from copy import deepcopy
from typing import Dict, Any, List

RULES_FILE = os.path.join('data', 'normalization_rules.json')

DEFAULT_RULES = {
    'name_aliases': {
        '袖套': ['套袖', '手袖', '护袖'],
        '手套': ['防护手套', '劳保手套', '工作手套'],
        '布手套': ['棉手套', '线手套', '纱手套'],
        '安全帽': ['防护帽', '头盔'],
        '口罩': ['防尘口罩', '防护口罩'],
        '劳保鞋': ['安全鞋', '防护鞋'],
        '雨鞋': ['雨靴', '胶鞋', '水鞋'],
        '反光背心': ['反光马甲', '安全背心', '警示背心'],
        '防护眼镜': ['护目镜', '防尘眼镜'],
        '耳塞': ['降噪耳塞', '防噪耳塞'],
        '防毒面具': ['防护面具', '呼吸面罩']
    },
    'unit_mappings': {
        '公斤': ['kg', 'KG', '千克'],
        '克': ['g', 'G'],
        '米': ['m', 'M', '公尺'],
        '厘米': ['cm', 'CM', '公分'],
        '毫米': ['mm', 'MM'],
        '升': ['l', 'L'],
        '毫升': ['ml', 'ML'],
        '双': ['付', '副'],
        '个': ['只', 'PCS', 'pcs'],
        '套': ['组'],
        '件': ['项'],
        '支': ['根'],
        '卷': ['盘'],
        '台': ['部']
    },
    'spec_patterns': [
        [r'\s+', ' '],
        [r'（', '('],
        [r'）', ')'],
        [r'【', '['],
        [r'】', ']'],
        [r'×', 'x'],
        [r'＊', 'x'],
        [r'X', 'x'],
        [r'﹣', '-'],
        [r'—', '-'],
        [r'－', '-'],
        [r'／', '/'],
        [r'，', ','],
        [r'：', ':']
    ]
}


def _ensure_parent_dir(path: str):
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


def _merge_unique_list(default_values: List[Any], custom_values: List[Any]) -> List[Any]:
    merged = []
    for value in list(default_values or []) + list(custom_values or []):
        if value not in merged:
            merged.append(value)
    return merged


def _merge_alias_mapping(default_mapping: Dict[str, List[Any]], custom_mapping: Dict[str, List[Any]]) -> Dict[str, List[Any]]:
    merged = deepcopy(default_mapping or {})
    for canonical, aliases in (custom_mapping or {}).items():
        merged[canonical] = _merge_unique_list(merged.get(canonical, []), aliases or [])
    return merged


def _merge_rules(custom_rules: Dict[str, Any]) -> Dict[str, Any]:
    custom_rules = custom_rules or {}
    return {
        'name_aliases': _merge_alias_mapping(DEFAULT_RULES.get('name_aliases', {}), custom_rules.get('name_aliases', {})),
        'unit_mappings': _merge_alias_mapping(DEFAULT_RULES.get('unit_mappings', {}), custom_rules.get('unit_mappings', {})),
        'spec_patterns': _merge_unique_list(DEFAULT_RULES.get('spec_patterns', []), custom_rules.get('spec_patterns', []))
    }


def load_normalization_rules() -> Dict[str, Any]:
    data = {}
    if os.path.exists(RULES_FILE):
        try:
            with open(RULES_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    data = loaded
        except Exception:
            data = {}

    merged = _merge_rules(data)

    if not os.path.exists(RULES_FILE):
        _ensure_parent_dir(RULES_FILE)
        with open(RULES_FILE, 'w', encoding='utf-8') as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)

    return merged


RULES = load_normalization_rules()


def reload_rules() -> Dict[str, Any]:
    global RULES
    RULES = load_normalization_rules()
    return RULES


def _clean_text(text: Any) -> str:
    if text is None:
        return ''
    return str(text).strip()


def _normalize_lookup_token(text: Any) -> str:
    value = _clean_text(text)
    if not value:
        return ''
    value = re.sub(r'[，,、/|｜]+', '', value)
    value = re.sub(r'[（）()\[\]【】]+', '', value)
    value = re.sub(r'\s+', '', value)
    return value.lower()


def normalize_name(text: Any) -> str:
    value = _clean_text(text)
    if not value:
        return ''

    compact_value = re.sub(r'\s+', '', value)
    lowered = _normalize_lookup_token(compact_value)

    for canonical, aliases in RULES.get('name_aliases', {}).items():
        candidates = [canonical] + list(aliases or [])
        for candidate in candidates:
            candidate_token = _normalize_lookup_token(candidate)
            if candidate_token and lowered == candidate_token:
                return canonical

    for canonical, aliases in RULES.get('name_aliases', {}).items():
        candidates = [canonical] + list(aliases or [])
        for candidate in candidates:
            candidate_token = _normalize_lookup_token(candidate)
            if candidate_token and len(candidate_token) >= 2 and candidate_token in lowered:
                return canonical

    return compact_value


def normalize_unit(text: Any) -> str:
    value = _clean_text(text)
    if not value:
        return ''

    lowered = _normalize_lookup_token(value)

    for canonical, aliases in RULES.get('unit_mappings', {}).items():
        candidates = [canonical] + list(aliases or [])
        for candidate in candidates:
            candidate_token = _normalize_lookup_token(candidate)
            if candidate_token and lowered == candidate_token:
                return canonical

    return re.sub(r'\s+', '', value)


def normalize_spec(text: Any) -> str:
    value = _clean_text(text)
    if not value:
        return ''

    for pattern, replacement in RULES.get('spec_patterns', []):
        value = re.sub(pattern, replacement, value)

    value = value.strip().lower()

    value = re.sub(r'gb\s*[-/]?\s*(\d+(?:[-/]\d+)*)', lambda m: f"GB{m.group(1).replace('/', '-')}", value, flags=re.IGNORECASE)
    value = re.sub(r'\s*x\s*', 'x', value)
    value = re.sub(r'\s+', ' ', value)

    return value.strip()


def normalize_numeric(text: Any):
    value = _clean_text(text)
    if not value:
        return ''

    value = value.replace(',', '')
    try:
        number = float(value)
        if number.is_integer():
            return int(number)
        return number
    except (TypeError, ValueError):
        return _clean_text(text)


def normalize_quote_item(item: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(item or {})
    normalized['normalized_name'] = normalize_name(item.get('name', ''))
    normalized['normalized_unit'] = normalize_unit(item.get('unit', ''))
    normalized['normalized_spec'] = normalize_spec(item.get('spec', ''))

    if 'quantity' in normalized:
        normalized['quantity'] = normalize_numeric(normalized.get('quantity'))
    if 'price' in normalized:
        normalized['price'] = normalize_numeric(normalized.get('price'))
    if 'seq' in normalized:
        normalized['seq'] = normalize_numeric(normalized.get('seq'))

    if not normalized.get('name') and normalized.get('normalized_name'):
        normalized['name'] = normalized['normalized_name']

    return normalized
