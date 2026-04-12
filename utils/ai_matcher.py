# -*- coding: utf-8 -*-
"""
AI增强匹配器
功能：融合传统规则 + AI语义匹配，提升匹配准确率
"""

import os
import sys
import asyncio
import logging
from typing import List, Dict, Any, Optional
from difflib import SequenceMatcher
import math

# 导入原有匹配器
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.matcher import (
    ProductMatcher,
    clean_nan,
    finalize_matches,
    get_feedback_hint,
    prepare_query_item,
    product_has_image,
)
from utils.ai_service import get_ai_service, AIService

logger = logging.getLogger(__name__)


class AIProductMatcher(ProductMatcher):
    """
    AI增强匹配器
    继承原有ProductMatcher，增加AI语义匹配能力
    """

    def __init__(self, products: List[Dict], ai_service: AIService = None):
        """
        初始化AI匹配器

        Args:
            products: 商品列表
            ai_service: AI服务实例（可选，默认使用全局实例）
        """
        super().__init__(products)
        self.ai_service = ai_service or get_ai_service()
        self.product_embeddings = {}  # 商品向量缓存
        self.use_ai = self.ai_service.is_available()

        # 从配置获取权重
        config = self.ai_service.config.get('matching', {})
        self.weights = config.get('weights', {
            'traditional': 0.35,
            'semantic': 0.40,
            'category': 0.15,
            'brand': 0.10
        })

        # AI特定阈值
        thresholds = config.get('thresholds', {})
        self.ai_auto_select_threshold = thresholds.get('auto_select', 0.60)
        self.ai_exact_match_threshold = thresholds.get('exact_match', 0.85)

        logger.info(f"AI Matcher initialized, use_ai={self.use_ai}, weights={self.weights}")

    async def _build_ai_index(self):
        """构建AI向量索引"""
        if not self.use_ai:
            return

        logger.info("Building AI embedding index...")
        count = 0

        for idx, product in enumerate(self.products):
            product_name = product.get('name', '')
            if product_name:
                try:
                    embedding = await self.ai_service._get_embedding_cached(product_name)
                    if embedding:
                        self.product_embeddings[idx] = embedding
                        count += 1
                except Exception as e:
                    logger.error(f"Failed to get embedding for product {idx}: {e}")

        logger.info(f"AI embedding index built: {count} products")

    async def ai_match_single(self, query_item: Dict, synonyms: Dict = None, feedback_provider=None) -> List[Dict]:
        """
        AI增强匹配单个报价项

        Args:
            query_item: 报价单项
            synonyms: 同义词字典

        Returns:
            匹配结果列表
        """
        if synonyms:
            self.synonyms = synonyms

        prepared_query = prepare_query_item(query_item)
        query_name = prepared_query.get('normalized_name') or prepared_query.get('name', '')
        query_spec = prepared_query.get('normalized_spec') or prepared_query.get('spec', '')
        query_brand = prepared_query.get('brand', '')

        if not query_name:
            return []

        # 1. 获取传统匹配结果
        traditional_matches = super().match_single(prepared_query, synonyms)

        # 如果AI不可用，直接返回传统结果
        if not self.use_ai:
            return traditional_matches

        # 2. AI语义匹配
        semantic_matches = await self._semantic_search(prepared_query)

        # 3. AI分类识别
        category_info = await self.ai_service.classify_product_category(query_name)

        # 4. AI品牌识别（如果没指定品牌）
        brand_info = {}
        if not query_brand:
            brand_info = await self.ai_service.recognize_brand(query_name)

        # 5. 融合评分
        feedback_summary = self.get_feedback_summary(prepared_query, feedback_provider)
        final_matches = self._combine_scores(
            traditional_matches=traditional_matches,
            semantic_matches=semantic_matches,
            category_info=category_info,
            brand_info=brand_info,
            query_item=prepared_query,
            feedback_summary=feedback_summary
        )

        final_matches = finalize_matches(final_matches, feedback_summary)

        return final_matches

    async def _semantic_search(self, query_item: Dict) -> List[Dict]:
        """
        语义向量搜索

        Args:
            query_item: 报价单项

        Returns:
            语义匹配结果列表
        """
        if not self.product_embeddings:
            await self._build_ai_index()

        if not self.product_embeddings:
            return []

        query_text = self._build_query_text(query_item)

        try:
            query_embedding = await self.ai_service._get_embedding_cached(query_text)
            if not query_embedding:
                return []
        except Exception as e:
            logger.error(f"Failed to get query embedding: {e}")
            return []

        # 计算与所有商品的语义相似度
        similarities = []
        for idx, product_embedding in self.product_embeddings.items():
            sim = self.ai_service._cosine_similarity(query_embedding, product_embedding)
            if sim >= 0.3:  # 最低相似度阈值
                similarities.append({
                    'index': idx,
                    'semantic_score': sim
                })

        # 按相似度排序
        similarities.sort(key=lambda x: x['semantic_score'], reverse=True)

        # 返回Top 20
        return similarities[:20]

    def _build_query_text(self, query_item: Dict) -> str:
        """构建查询文本"""
        parts = []

        if query_item.get('name'):
            parts.append(query_item['name'])

        if query_item.get('spec'):
            parts.append(query_item['spec'])

        if query_item.get('brand'):
            parts.append(query_item['brand'])

        if query_item.get('remark'):
            parts.append(query_item['remark'])

        return ' '.join(parts)

    def _combine_scores(self, traditional_matches: List[Dict], semantic_matches: List[Dict],
                        category_info: Dict, brand_info: Dict, query_item: Dict,
                        feedback_summary: Optional[Dict] = None) -> List[Dict]:
        """
        融合传统规则和AI结果的评分

        Args:
            traditional_matches: 传统匹配结果
            semantic_matches: 语义匹配结果
            category_info: AI分类信息
            brand_info: AI品牌信息
            query_item: 原始查询项

        Returns:
            融合后的匹配结果
        """
        # 创建索引映射
        traditional_map = {m['index']: m for m in traditional_matches}
        semantic_map = {m['index']: m['semantic_score'] for m in semantic_matches}

        # 收集所有候选索引
        all_indices = set(traditional_map.keys()) | set(semantic_map.keys())

        results = []
        weights = self.weights

        for idx in all_indices:
            # 获取传统匹配数据
            trad_match = traditional_map.get(idx, {})
            trad_score = trad_match.get('base_score', trad_match.get('score', 0))
            product = trad_match.get('product')

            # 如果传统匹配没有这个商品，从商品库获取
            if not product and idx < len(self.products):
                product = self.products[idx]

            if not product:
                continue

            # 获取语义分数
            semantic_score = semantic_map.get(idx, 0)

            # 分类匹配分数
            category_score = 0
            if category_info.get('category'):
                product_category = product.get('category', '')
                if category_info['category'] in product_category:
                    category_score = 0.8
                else:
                    category_score = 0.3

            # 品牌匹配分数
            brand_score = 0
            product_brand = product.get('brand', '')
            query_brand = query_item.get('brand', '') or brand_info.get('brand', '')

            if query_brand:
                if query_brand.lower() == product_brand.lower():
                    brand_score = 1.0
                elif query_brand.lower() in product_brand.lower() or product_brand.lower() in query_brand.lower():
                    brand_score = 0.7

            # 综合评分
            final_score = (
                trad_score * weights.get('traditional', 0.35) +
                semantic_score * weights.get('semantic', 0.40) +
                category_score * weights.get('category', 0.15) +
                brand_score * weights.get('brand', 0.10)
            )

            # 限制最高分
            final_score = min(final_score, 1.0)

            # 构建结果
            result = {
                'index': idx,
                'product': product,
                'score': round(final_score, 3),
                'match_type': 'exact' if final_score >= self.ai_exact_match_threshold else 'fuzzy',
                'brand_matched': brand_score > 0.5,
                'ai_enhanced': True,
                'score_details': {
                    'traditional': round(trad_score, 3),
                    'semantic': round(semantic_score, 3),
                    'category': round(category_score, 3),
                    'brand': round(brand_score, 3),
                    'similarity': round(trad_match.get('score_details', {}).get('similarity', 0), 3) if trad_match else 0,
                    'type_match': round(trad_match.get('score_details', {}).get('type_match', 0), 3) if trad_match else 0,
                    'keyword_overlap': round(trad_match.get('score_details', {}).get('keyword_overlap', 0), 3) if trad_match else 0,
                },
                'feedback_summary': {
                    'feedback_count': int((feedback_summary or {}).get('feedback_count', 0) or 0),
                    'no_match_count': round(float((feedback_summary or {}).get('no_match_count', 0) or 0), 2),
                    'ask_boss_count': round(float((feedback_summary or {}).get('ask_boss_count', 0) or 0), 2)
                }
            }

            results.append(result)

        # 按综合分数排序
        results.sort(key=lambda x: x['score'], reverse=True)

        return results[:20]

    def match_single(self, query_item: Dict, synonyms: Dict = None, feedback_provider=None) -> List[Dict]:
        """
        匹配单个报价项（同步接口）

        兼容原有接口，支持降级到传统匹配
        """
        prepared_query = prepare_query_item(query_item)
        if self.use_ai:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(self.ai_match_single(prepared_query, synonyms, feedback_provider=feedback_provider))
                loop.close()
                return clean_nan(result)
            except Exception as e:
                logger.error(f"AI match failed, fallback to traditional: {e}")
                return super().match_single(prepared_query, synonyms, feedback_provider=feedback_provider)
        else:
            return super().match_single(prepared_query, synonyms, feedback_provider=feedback_provider)

    def _build_result_row(self, idx: int, item: Dict, matches: List[Dict], feedback_summary: Optional[Dict] = None,
                          auto_threshold: float = None) -> Dict:
        prepared_item = prepare_query_item(item)
        best_match = matches[0] if matches else None
        alternatives = []
        if not matches or (best_match and best_match['score'] < 0.4):
            alternatives = self.find_alternatives(prepared_item, limit=5)

        feedback_summary = feedback_summary or {}
        learned_auto_threshold = 0.45 if int(feedback_summary.get('feedback_count', 0) or 0) >= 3 else self.ai_auto_select_threshold
        threshold = learned_auto_threshold if auto_threshold is None else auto_threshold
        auto_action = None
        auto_selected = None
        if best_match and best_match['score'] >= threshold:
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
            'ai_enhanced': self.use_ai,
            'feedback_hint': get_feedback_hint(feedback_summary),
            'feedback_summary': {
                'feedback_count': int(feedback_summary.get('feedback_count', 0) or 0),
                'no_match_count': round(float(feedback_summary.get('no_match_count', 0) or 0), 2),
                'ask_boss_count': round(float(feedback_summary.get('ask_boss_count', 0) or 0), 2)
            },
            'source_type': prepared_item.get('source_type', ''),
            'query_signature': prepared_item.get('query_signature', ''),
            'image_assisted': any(product_has_image(match.get('product') or {}) for match in matches[:3])
        }
        return clean_nan(result)

    def match_all(self, query_items: List[Dict], synonyms: Dict = None, feedback_provider=None) -> List[Dict]:
        """
        批量匹配所有报价项（同步接口）

        兼容原有接口
        """
        prepared_items = [prepare_query_item(item) for item in (query_items or [])]
        if self.use_ai:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(self.ai_match_all(prepared_items, synonyms, feedback_provider=feedback_provider))
                loop.close()
                return clean_nan(result)
            except Exception as e:
                logger.error(f"AI batch match failed, fallback: {e}")
                return super().match_all(prepared_items, synonyms, feedback_provider=feedback_provider)
        else:
            return super().match_all(prepared_items, synonyms, feedback_provider=feedback_provider)

    async def ai_match_all(self, query_items: List[Dict], synonyms: Dict = None, feedback_provider=None) -> List[Dict]:
        """
        AI批量匹配（异步）

        Args:
            query_items: 报价单列表
            synonyms: 同义词字典

        Returns:
            匹配结果列表
        """
        if synonyms:
            self.synonyms = synonyms

        if self.use_ai:
            await self._build_ai_index()

        results = []

        for idx, item in enumerate(query_items):
            try:
                prepared_item = prepare_query_item(item)
                if self.use_ai:
                    matches = await self.ai_match_single(prepared_item, synonyms, feedback_provider=feedback_provider)
                else:
                    matches = super().match_single(prepared_item, synonyms, feedback_provider=feedback_provider)

                feedback_summary = self.get_feedback_summary(prepared_item, feedback_provider)
                result = self._build_result_row(idx, prepared_item, matches, feedback_summary=feedback_summary)
                result['ai_enhanced'] = self.use_ai
                results.append(result)

            except Exception as e:
                logger.error(f"Match error for item {idx}: {e}")
                prepared_item = prepare_query_item(item)
                results.append({
                    'index': idx,
                    'query_item': prepared_item,
                    'matches': [],
                    'best_match': None,
                    'alternatives': [],
                    'confirmed': False,
                    'action': None,
                    'selected_product': None,
                    'ai_enhanced': False,
                    'feedback_hint': '',
                    'feedback_summary': {
                        'feedback_count': 0,
                        'no_match_count': 0,
                        'ask_boss_count': 0
                    },
                    'source_type': prepared_item.get('source_type', ''),
                    'query_signature': prepared_item.get('query_signature', ''),
                    'image_assisted': False,
                    'error': str(e)
                })

        return clean_nan(results)



# create_matcher defined above


def create_matcher(products: List[Dict], use_ai: bool = True) -> ProductMatcher:
    """
    创建匹配器工厂函数

    Args:
        products: 商品列表
        use_ai: 是否使用AI增强

    Returns:
        匹配器实例
    """
    if use_ai:
        ai_service = get_ai_service()
        if ai_service.is_available():
            return AIProductMatcher(products, ai_service)

    # 降级到传统匹配器
    return ProductMatcher(products)