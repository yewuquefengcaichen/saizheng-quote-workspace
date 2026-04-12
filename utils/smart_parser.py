# -*- coding: utf-8 -*-
"""
智能报价单解析器
功能：自动识别任意格式报价单的列含义
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
import re
from datetime import datetime
from utils.normalizer import normalize_quote_item


class SmartQuoteParser:
    """智能报价单解析器"""

    # 列类型关键词定义
    COLUMN_KEYWORDS = {
        'name': {
            'keywords': ['产品名称', '物资名称', '品名', '商品名', '名称', '货品名', '产品',
                        'item', 'product', '物资', '货物名称', '材料名称', '商品名称'],
            'weight': 1.0
        },
        'quantity': {
            'keywords': ['数量', '需求数量', '需求量', 'qty', 'quantity', 'count',
                        '计划数量', '采购数量', '订货数量', '数量（', '数量('],
            'weight': 1.0
        },
        'unit': {
            'keywords': ['单位', '计量单位', 'uom', 'unit', '单位名称', '计量',
                        '基本单位', '数量单位'],
            'weight': 1.0
        },
        'price': {
            'keywords': ['单价', '预算单价', '价格', '销售单价', '采购单价', '含税单价',
                        '单价（元）', '单价(元)', '预算价格', '单价（', '单价(',
                        '总价', '预算单价（元）', '金额（元）', '金额(元)', '报价单价'],
            'weight': 1.0
        },
        'spec': {
            'keywords': ['规格', '型号', '规格型号', 'spec', '型号规格',
                        '规格（', '规格(', '参数', '技术参数', '规格/材质', '材质'],
            'weight': 0.8
        },
        'color': {
            'keywords': ['颜色', '色号', '色彩', 'color', '颜色（', '颜色('],
            'weight': 1.0
        },
        'remark': {
            'keywords': ['备注', '说明', '要求', '技术参数', 'remark', '备注说明',
                        '技术要求', '特殊要求', '备注（', '备注('],
            'weight': 0.7
        },
        'seq': {
            'keywords': ['序号', 'no', '编号', 'no.', '序 号', '序  号',
                        '项号', '项目编号', '序号（', '序号('],
            'weight': 1.0
        },
        'brand': {
            'keywords': ['品牌', 'brand', '品牌/生产厂家', '生产厂家', '厂商',
                        '品牌型号', '报价品牌', '品牌名称', '推荐品牌'],
            'weight': 1.0
        },
        'category': {
            'keywords': ['类别', '分类', 'category', '商品类别', '物资类别',
                        '类型', '品类'],
            'weight': 0.6
        },
        'image': {
            'keywords': ['图片', '照片', 'image', 'img', '产品图片', '产品图',
                        '商品图片', '实物图', '报价产品图片'],
            'weight': 1.0
        },
        'ignore': {
            'keywords': ['备注说明', '其他', 'ignore', '供应商', '供货商', '厂家'],
            'weight': 0.3
        }
    }

    # 数据类型特征
    DATA_TYPE_PATTERNS = {
        'seq': r'^\d{1,4}$',  # 序号：1-4位数字
        'quantity': r'^\d+\.?\d*$',  # 数量：数字
        'price': r'^\d+\.?\d{0,2}$',  # 价格：数字，最多2位小数
        'name': r'[\u4e00-\u9fa5a-zA-Z]',  # 名称：含中文或英文
    }

    def __init__(self):
        self.df = None
        self.header_start_row = 0
        self.header_rows = 0
        self.data_start_row = 0
        self.column_mapping = {}
        self.parse_result = {}
        self.is_horizontal = False  # 是否横向布局

    def parse(self, file, templates: List[Dict] = None) -> Dict[str, Any]:
        """
        解析报价单

        Args:
            file: 上传的文件对象
            templates: 已保存的模板列表（用于自动匹配）

        Returns:
            解析结果字典
        """
        # 读取Excel或CSV原始数据
        try:
            if hasattr(file, 'filename') and file.filename.lower().endswith('.csv'):
                self.df = pd.read_csv(file, encoding='utf-8-sig', header=None)
            else:
                self.df = pd.read_excel(
                    file,
                    engine='xlrd' if file.filename.endswith('.xls') else 'openpyxl',
                    header=None
                )
        except Exception as e:
            # 尝试其他引擎
            try:
                self.df = pd.read_excel(file, header=None)
            except Exception as e2:
                raise Exception(f"无法读取Excel文件: {str(e2)}")

        print(f"=== 智能解析报价单 ===")
        print(f"文件: {file.filename}")
        print(f"总行数: {len(self.df)}, 总列数: {len(self.df.columns)}")

        # 检测是否为横向布局
        self._detect_horizontal_layout()

        # 步骤1: 识别表头区域
        self._detect_header_region()

        # 步骤2: 识别每列含义
        self._identify_columns()

        # 步骤3: 识别数据起始行
        self._detect_data_start()

        # 步骤4: 提取预览数据
        preview_data = self._extract_preview()

        # 步骤5: 尝试匹配模板
        matched_template = None
        if templates:
            matched_template = self._match_template(templates)

        # 提取标识符（用于保存模板时）
        identifiers = self._extract_identifiers()

        # 构建结果
        self.parse_result = {
            'success': True,
            'source': 'excel',
            'total_rows': len(self.df),
            'total_cols': len(self.df.columns),
            'header_rows': self.header_rows,
            'data_start_row': self.data_start_row,
            'column_mapping': self.column_mapping,
            'preview': preview_data,
            'raw_headers': self._get_raw_headers(),
            'is_horizontal': self.is_horizontal,
            'matched_template': matched_template,
            'identifiers': identifiers,
            'header_signature': self._build_header_signature(),
            'identifier_signature': self._build_identifier_signature()
        }

        return self.parse_result

    def _extract_identifiers(self) -> List[str]:
        """提取表头标识符（用于模板匹配）"""
        identifiers = []
        header_end_row = min(self.header_start_row + self.header_rows, len(self.df))
        for row_idx in range(self.header_start_row, min(header_end_row, self.header_start_row + 3)):
            for col_idx in range(min(len(self.df.columns), 10)):
                val = self.df.iloc[row_idx, col_idx]
                if pd.notna(val):
                    val_str = str(val).strip()
                    if val_str and len(val_str) >= 2 and len(val_str) <= 20:
                        identifiers.append(val_str)
        return list(set(identifiers))[:20]  # 最多20个标识符

    def _build_header_signature(self) -> str:
        """构建表头签名"""
        headers = [str(h).strip().lower() for h in self._get_raw_headers() if str(h).strip()]
        return '|'.join(headers[:20])

    def _build_identifier_signature(self) -> str:
        """构建标识符签名"""
        identifiers = sorted(str(v).strip().lower() for v in self._extract_identifiers() if str(v).strip())
        return '|'.join(identifiers[:20])

    @staticmethod
    def mapping_to_signature(mapping: Dict[int, str]) -> str:
        """将列映射规范化成稳定签名"""
        normalized_pairs = []
        for col_idx, col_type in (mapping or {}).items():
            try:
                normalized_idx = int(col_idx)
            except (TypeError, ValueError):
                normalized_idx = str(col_idx)
            normalized_pairs.append((normalized_idx, str(col_type or '').strip()))
        normalized_pairs.sort(key=lambda item: str(item[0]))
        return '|'.join(f"{col}:{field}" for col, field in normalized_pairs if field)

    @classmethod
    def score_template_match(cls, parse_features: Dict[str, Any], template: Dict[str, Any]) -> float:
        """计算模板匹配分数，供 Excel 与 OCR 共用"""
        parse_features = parse_features or {}
        template = template or {}

        current_identifiers = set(parse_features.get('identifiers') or [])
        current_headers = set(parse_features.get('raw_headers') or [])
        current_header_signature = parse_features.get('header_signature', '')
        current_identifier_signature = parse_features.get('identifier_signature', '')
        current_source = parse_features.get('source_type', 'excel')

        template_identifiers = set(template.get('identifiers', []))
        template_mapping = template.get('last_confirmed_mapping') or template.get('column_mapping', {})
        if not template_identifiers and not template.get('identifier_signature'):
            return 0.0

        intersection = current_identifiers & template_identifiers
        score = len(intersection) / len(template_identifiers) if template_identifiers else 0.0

        if len(current_headers) == len(template_mapping):
            score += 0.1

        if current_header_signature and template.get('header_signature') == current_header_signature:
            score += 0.25

        if current_identifier_signature and template.get('identifier_signature') == current_identifier_signature:
            score += 0.2

        usage_count = int(template.get('usage_count') or 0)
        confirm_count = int(template.get('confirm_count') or 0)
        manual_save_count = int(template.get('manual_save_count') or 0)
        mapping_change_count = int(template.get('mapping_change_count') or 0)

        score += min(usage_count, 10) * 0.015
        score += min(confirm_count, 12) * 0.012
        score += min(manual_save_count, 6) * 0.01
        score -= min(mapping_change_count, 6) * 0.018

        if template.get('source_type') == current_source:
            score += 0.08

        last_used_at = template.get('last_used_at')
        if last_used_at:
            try:
                used_at = datetime.strptime(last_used_at, '%Y-%m-%d %H:%M:%S')
                days_since = max((datetime.now() - used_at).days, 0)
                score += max(0, 0.12 - min(days_since, 30) * 0.004)
            except Exception:
                pass

        return round(max(score, 0.0), 4)

    @classmethod
    def match_template_for_result(cls, parse_result: Dict[str, Any], templates: List[Dict]) -> Optional[Dict]:
        """根据 parse_result 特征匹配模板"""
        parse_features = {
            'identifiers': parse_result.get('identifiers', []),
            'raw_headers': parse_result.get('raw_headers', []),
            'header_signature': parse_result.get('header_signature', ''),
            'identifier_signature': parse_result.get('identifier_signature', ''),
            'source_type': parse_result.get('source', 'excel')
        }

        best_match = None
        best_score = 0.0
        for template in templates or []:
            score = cls.score_template_match(parse_features, template)
            print(f"模板 '{template.get('name')}' 匹配分数: {score:.2f}")
            if score >= 0.6 and score > best_score:
                best_score = score
                best_match = dict(template)
                template_mapping = template.get('last_confirmed_mapping') or template.get('column_mapping', {})
                if template_mapping:
                    best_match['column_mapping'] = template_mapping
                best_match['matched_score'] = round(score, 3)

        if best_match:
            print(f"匹配到模板: {best_match.get('name')} (分数: {best_score:.2f})")
        return best_match

    def _match_template(self, templates: List[Dict]) -> Optional[Dict]:
        """尝试匹配已保存的模板"""
        parse_result = {
            'identifiers': self._extract_identifiers(),
            'raw_headers': self._get_raw_headers(),
            'header_signature': self._build_header_signature(),
            'identifier_signature': self._build_identifier_signature(),
            'source': self.parse_result.get('source', 'excel') if isinstance(self.parse_result, dict) else 'excel'
        }
        return self.match_template_for_result(parse_result, templates)

    def get_template_features(self, source_type: str = 'excel') -> Dict[str, Any]:
        """返回当前解析结果对应的模板特征"""
        return {
            'source_type': source_type,
            'identifiers': self._extract_identifiers(),
            'header_signature': self._build_header_signature(),
            'identifier_signature': self._build_identifier_signature(),
            'raw_headers': self._get_raw_headers(),
            'header_rows': self.header_rows
        }

    @classmethod
    def build_template_payload_from_result(
        cls,
        parse_result: Dict[str, Any],
        name: str,
        confirmed_mapping: Dict[int, str],
        source_type: str = 'excel',
        manual_save: bool = False,
        template_hit: bool = False,
        previous_mapping: Dict[int, str] = None
    ) -> Dict[str, Any]:
        """根据 parse_result 构建模板载荷，供 Excel 与 OCR 统一复用"""
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        mapping_signature = cls.mapping_to_signature(confirmed_mapping)
        changed = bool(previous_mapping) and cls.mapping_to_signature(previous_mapping) != mapping_signature
        return {
            'name': name,
            'column_mapping': confirmed_mapping,
            'last_confirmed_mapping': confirmed_mapping,
            'header_rows': parse_result.get('header_rows', 1),
            'identifiers': parse_result.get('identifiers', []),
            'header_signature': parse_result.get('header_signature', ''),
            'identifier_signature': parse_result.get('identifier_signature', ''),
            'source_type': source_type,
            'usage_count': 1,
            'confirm_count': 1,
            'manual_save_count': 1 if manual_save else 0,
            'template_hit_count': 1 if template_hit else 0,
            'mapping_change_count': 1 if changed else 0,
            'mapping_signature': mapping_signature,
            'last_mapping_changed': changed,
            'last_used_at': now,
            'created_at': now,
            'updated_at': now
        }

    @classmethod
    def register_template_usage_for_result(
        cls,
        template: Dict[str, Any],
        parse_result: Dict[str, Any],
        confirmed_mapping: Dict[int, str],
        source_type: str = 'excel',
        manual_save: bool = False,
        template_hit: bool = False
    ) -> Dict[str, Any]:
        """根据 parse_result 更新模板学习字段"""
        updated = dict(template or {})
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        previous_mapping = updated.get('last_confirmed_mapping') or updated.get('column_mapping') or {}
        previous_signature = cls.mapping_to_signature(previous_mapping)
        current_signature = cls.mapping_to_signature(confirmed_mapping)
        mapping_changed = bool(previous_signature and previous_signature != current_signature)

        updated['column_mapping'] = confirmed_mapping
        updated['last_confirmed_mapping'] = confirmed_mapping
        updated['identifiers'] = parse_result.get('identifiers', [])
        updated['header_signature'] = parse_result.get('header_signature', '')
        updated['identifier_signature'] = parse_result.get('identifier_signature', '')
        updated['header_rows'] = parse_result.get('header_rows', 1)
        updated['source_type'] = source_type
        updated['usage_count'] = int(updated.get('usage_count') or 0) + 1
        updated['confirm_count'] = int(updated.get('confirm_count') or 0) + 1
        updated['manual_save_count'] = int(updated.get('manual_save_count') or 0) + (1 if manual_save else 0)
        updated['template_hit_count'] = int(updated.get('template_hit_count') or 0) + (1 if template_hit else 0)
        updated['mapping_change_count'] = int(updated.get('mapping_change_count') or 0) + (1 if mapping_changed else 0)
        updated['mapping_signature'] = current_signature
        updated['last_mapping_changed'] = mapping_changed
        updated['last_used_at'] = now
        updated['updated_at'] = now
        updated.setdefault('created_at', now)
        return updated

    def normalize_items(self, items: List[Dict]) -> List[Dict]:
        """统一标准化报价项"""
        return [normalize_quote_item(item) for item in items]

    def get_normalized_items(self, confirmed_mapping: Dict[int, str] = None) -> List[Dict]:
        """提取并标准化报价项"""
        return self.normalize_items(self.get_parsed_items(confirmed_mapping))

    def apply_learned_mapping(self, confirmed_mapping: Dict[int, str]):
        """将用户确认后的映射回写到当前解析结果"""
        for col_idx, col_type in confirmed_mapping.items():
            if col_idx in self.column_mapping:
                self.column_mapping[col_idx]['detected_type'] = col_type
                self.column_mapping[col_idx]['needs_confirm'] = False
                self.column_mapping[col_idx]['confidence'] = max(self.column_mapping[col_idx].get('confidence', 0), 0.99)

        if isinstance(self.parse_result, dict):
            self.parse_result['column_mapping'] = self.column_mapping
            self.parse_result['identifiers'] = self._extract_identifiers()
            self.parse_result['header_signature'] = self._build_header_signature()
            self.parse_result['identifier_signature'] = self._build_identifier_signature()
            self.parse_result['last_confirmed_mapping'] = confirmed_mapping
            self.parse_result['source'] = self.parse_result.get('source', 'excel')

        return self.column_mapping

    def enrich_parse_result(self, parse_result: Dict[str, Any], source_type: str = 'excel') -> Dict[str, Any]:
        """补充模板学习相关特征到解析结果"""
        enriched = dict(parse_result or {})
        features = self.get_template_features(source_type)
        enriched['source'] = enriched.get('source', source_type)
        enriched['identifiers'] = enriched.get('identifiers') or features['identifiers']
        enriched['header_signature'] = enriched.get('header_signature') or features['header_signature']
        enriched['identifier_signature'] = enriched.get('identifier_signature') or features['identifier_signature']
        enriched['raw_headers'] = enriched.get('raw_headers') or features['raw_headers']
        enriched['header_rows'] = enriched.get('header_rows') or features['header_rows']
        return enriched

    def build_template_payload(self, name: str, confirmed_mapping: Dict[int, str], source_type: str = 'excel') -> Dict[str, Any]:
        """生成模板保存载荷"""
        return self.build_template_payload_from_result(
            self.enrich_parse_result({}, source_type),
            name,
            confirmed_mapping,
            source_type
        )

    def register_template_usage(self, template: Dict, confirmed_mapping: Dict[int, str], source_type: str = 'excel') -> Dict[str, Any]:
        """更新模板命中后的学习字段"""
        return self.register_template_usage_for_result(
            template,
            self.enrich_parse_result({}, source_type),
            confirmed_mapping,
            source_type,
            manual_save=False,
            template_hit=True
        )

    @classmethod
    def apply_template_learning_to_result(
        cls,
        parse_result: Dict[str, Any],
        confirmed_mapping: Dict[int, str],
        source_type: str = 'excel'
    ) -> Dict[str, Any]:
        """补充任意 parse_result 的模板学习字段"""
        updated = dict(parse_result or {})
        updated['column_mapping'] = confirmed_mapping
        updated['last_confirmed_mapping'] = confirmed_mapping
        updated['source'] = updated.get('source', source_type)
        updated['header_rows'] = updated.get('header_rows', 1)
        updated['identifiers'] = updated.get('identifiers', [])
        updated['header_signature'] = updated.get('header_signature', '')
        updated['identifier_signature'] = updated.get('identifier_signature', '')
        return updated

    def apply_template_learning(self, confirmed_mapping: Dict[int, str], source_type: str = 'excel') -> Dict[str, Any]:
        """回写当前 parse_result 的模板学习字段"""
        self.parse_result = self.apply_template_learning_to_result(self.parse_result, confirmed_mapping, source_type)
        return self.parse_result

    def _detect_header_region(self):
        """识别表头区域（可能占多行）"""
        # 策略：
        # 1. 跳过标题行（大部分为空的行）
        # 2. 表头行包含字段标签关键词
        # 3. 数据行包含实际数值

        # 先找第一个有足够内容的行作为起始
        first_content_row = 0
        for idx, row in self.df.iterrows():
            non_empty = sum(1 for v in row.values if pd.notna(v) and str(v).strip())
            if non_empty >= 3:
                first_content_row = idx
                break

        self.header_start_row = first_content_row
        print(f"第一个有内容的行: {first_content_row}")

        if first_content_row > 0:
            print(f"检测到顶部标题行，将从第 {first_content_row} 行开始识别表头")

        # 检测关键词（用于识别表头）
        header_keywords = ['名称', '单位', '数量', '价格', '单价', '规格',
                          '品牌', '备注', '序号', '物资', '计量', '预算',
                          '总价', '含税', '型号', 'item', 'name', 'qty',
                          '技术要求', '图片', '编码']

        header_score = []
        for idx, row in self.df.iterrows():
            text_count = 0
            number_count = 0
            empty_count = 0
            large_number_count = 0
            keyword_count = 0
            short_text_count = 0  # 短文本数量（表头通常是短文本）
            first_non_empty = ''

            for val in row.values:
                if pd.isna(val) or str(val).strip() == '':
                    empty_count += 1
                else:
                    val_str = str(val).strip()
                    if not first_non_empty:
                        first_non_empty = val_str

                    # 检查是否是短文本（<=20字符）
                    if len(val_str) <= 20:
                        short_text_count += 1
                        # 只有短文本才检查关键词（避免长文本中的误匹配）
                        for kw in header_keywords:
                            if kw.lower() in val_str.lower():
                                keyword_count += 1
                                break

                    # 判断是数字还是文本
                    try:
                        num_val = float(val_str)
                        number_count += 1
                        if num_val > 100:
                            large_number_count += 1
                    except:
                        text_count += 1

            total = len(row.values)
            non_empty = text_count + number_count
            starts_with_number = bool(re.match(r'^\d+(?:\.\d+)?$', first_non_empty))

            # 计算评分
            # 表头特征：有关键词、短文本多、没有明显数据模式
            # 数据行特征：首列为序号、数字列明显、关键词少
            if starts_with_number and non_empty >= 4 and keyword_count == 0:
                score = 0.1  # 典型数据行：序号开头
            elif number_count >= 2 and keyword_count == 0 and text_count >= 1:
                score = 0.1  # 同时包含序号/价格等多个数字，倾向数据行
            elif large_number_count >= 2:
                score = 0.1  # 明确的数据行
            elif keyword_count >= 2 and short_text_count >= total * 0.5:
                score = 0.9  # 明确的表头行（短文本+关键词）
            elif keyword_count >= 1 and short_text_count >= total * 0.6:
                score = 0.7  # 可能是表头
            elif short_text_count >= total * 0.8 and text_count >= total * 0.5:
                # 大部分是短文本且大部分是文本，可能是表头
                score = 0.6
            else:
                score = 0.2  # 默认当作数据行

            header_score.append(score)
            if idx < 10:
                print(f"行 {idx}: 文本={text_count}, 数字={number_count}, 大数字={large_number_count}, 关键词={keyword_count}, 短文本={short_text_count}, 首值={first_non_empty}, 评分={score:.2f}")

        # 找到表头区域
        # 从第一个有内容的行开始，统计连续的表头行数
        header_end_row = min(first_content_row + 1, len(self.df))
        for idx in range(first_content_row + 1, len(header_score)):
            score = header_score[idx]
            if score >= 0.6:
                header_end_row = idx + 1
            else:
                break

        # 限制最大表头行数
        self.header_rows = header_end_row - first_content_row
        self.header_rows = min(self.header_rows, 5)
        self.header_rows = max(1, self.header_rows)

        print(f"识别到表头起始行: {self.header_start_row}")
        print(f"识别到表头行数: {self.header_rows}")
        print(f"推断数据开始行: {self.header_start_row + self.header_rows}")

        self.data_start_row = self.header_start_row + self.header_rows

        if self.data_start_row >= len(self.df):
            self.data_start_row = max(self.header_start_row + 1, len(self.df) - 1)
        elif self.data_start_row < len(self.df):
            first_data_row = self.df.iloc[self.data_start_row]
            non_empty = [v for v in first_data_row.values if pd.notna(v) and str(v).strip()]
            if len(non_empty) < 2 and self.data_start_row > self.header_start_row:
                self.data_start_row = self.header_start_row + self.header_rows

        print(f"初始数据起始行: {self.data_start_row}")

        self.header_rows = max(1, self.data_start_row - self.header_start_row)
        print(f"最终表头行数: {self.header_rows}")


































































































    def _detect_horizontal_layout(self):
        """检测是否为横向布局（产品作为列）"""
        # 横向布局特征：
        # 真正的横向布局：第一列是属性名（名称、单位、数量...），每列是一个产品
        # 纵向布局：第一行是属性名，每行是一个产品

        if len(self.df.columns) < 3 or len(self.df) < 3:
            self.is_horizontal = False
            return

        # 检查关键词
        keywords = ['名称', '单位', '数量', '价格', '单价', '规格',
                    '品牌', '备注', '序号', '物资', '计量', '预算',
                    '总价', '含税', '质保', '型号', '颜色']

        # 方法1: 检查第一行是否包含大量关键词
        first_row_text = []
        for col_idx in range(min(15, len(self.df.columns))):
            val = self.df.iloc[0, col_idx]
            if pd.notna(val):
                first_row_text.append(str(val).strip())
        first_row_str = ' '.join(first_row_text)
        print(f"第一行内容: {first_row_str[:100]}...")
        row_keyword_count = sum(1 for kw in keywords if kw in first_row_str)

        # 方法2: 检查第一列是否包含大量关键词
        first_col_text = []
        for row_idx in range(min(15, len(self.df))):
            val = self.df.iloc[row_idx, 0]
            if pd.notna(val):
                first_col_text.append(str(val).strip())
        first_col_str = ' '.join(first_col_text)
        print(f"第一列内容: {first_col_str[:100]}...")
        col_keyword_count = sum(1 for kw in keywords if kw in first_col_str)

        print(f"横向布局检测: 第一行关键词={row_keyword_count}, 第一列关键词={col_keyword_count}")

        # 判断逻辑：
        # - 第一行有很多关键词，第一列没有 → 正常纵向布局（不需要转置）
        # - 第一列有很多关键词，第一行没有 → 横向布局（需要转置）
        # - 两者都有 → 可能是复杂表头，保持原样

        if col_keyword_count >= 4 and row_keyword_count < 3:
            # 第一列有大量关键词，第一行没有 → 横向布局
            self.is_horizontal = True
            print("检测到横向布局（产品在列），将进行转置处理")
            self._transpose_data()
        else:
            # 其他情况都当作纵向布局处理
            self.is_horizontal = False

    def _transpose_data(self):
        """转置数据（将横向布局转为纵向）"""
        # 转置DataFrame
        self.df = self.df.T
        # 重置索引
        self.df = self.df.reset_index(drop=True)
        print(f"转置后: 行数={len(self.df)}, 列数={len(self.df.columns)}")

    def _identify_columns(self):
        """识别每列的含义"""
        self.column_mapping = {}

        # 获取表头文本（合并多行表头）
        header_texts = []
        header_end_row = min(self.header_start_row + self.header_rows, len(self.df))
        for col_idx in range(len(self.df.columns)):
            texts = []
            for row_idx in range(self.header_start_row, header_end_row):
                val = self.df.iloc[row_idx, col_idx]
                if pd.notna(val) and str(val).strip():
                    texts.append(str(val).strip())
            header_texts.append(' '.join(texts))

        self.data_start_row = max(self.data_start_row, self.header_start_row + self.header_rows)

        print(f"表头文本: {header_texts}")

        # 对每列进行识别
        for col_idx, header_text in enumerate(header_texts):
            best_match = self._match_column_type(header_text, col_idx)
            self.column_mapping[col_idx] = best_match

        print(f"列映射结果: {self.column_mapping}")

    def _match_column_type(self, header_text: str, col_idx: int) -> Dict:
        """匹配列类型"""
        header_lower = header_text.lower()
        scores = {}

        # 关键词匹配
        for col_type, config in self.COLUMN_KEYWORDS.items():
            score = 0
            for keyword in config['keywords']:
                if keyword.lower() in header_lower:
                    # 完全匹配加分
                    if keyword.lower() == header_lower:
                        score += 2.0
                    else:
                        score += config['weight']
            scores[col_type] = score

        # 分析该列的数据特征
        data_scores = self._analyze_data_pattern(col_idx)
        for col_type, score in data_scores.items():
            if col_type in scores:
                scores[col_type] += score * 0.5
            else:
                scores[col_type] = score * 0.5

        # 找出最佳匹配
        best_type = None
        best_score = 0
        for col_type, score in scores.items():
            if score > best_score:
                best_score = score
                best_type = col_type

        return {
            'original_header': header_text,
            'detected_type': best_type if best_type else '',
            'confidence': min(best_score / 2, 1.0) if best_type else 0,
            'scores': scores,
            'needs_confirm': best_score < 1.0
        }

    def _analyze_data_pattern(self, col_idx: int) -> Dict[str, float]:
        """分析该列的数据模式"""
        scores = {}

        # 取表头后的几行数据进行分析
        sample_data = []
        sample_start = self.header_start_row + self.header_rows
        sample_end = min(sample_start + 10, len(self.df))
        for row_idx in range(sample_start, sample_end):
            val = self.df.iloc[row_idx, col_idx]
            if pd.notna(val):
                sample_data.append(val)

        if not sample_data:
            return scores

        # 分析数据特征
        number_count = 0
        text_count = 0
        chinese_count = 0

        for val in sample_data:
            val_str = str(val).strip()
            try:
                float(val_str)
                number_count += 1
            except:
                text_count += 1
                if re.search(r'[\u4e00-\u9fa5]', val_str):
                    chinese_count += 1

        total = len(sample_data)

        # 根据特征判断
        if number_count / total > 0.7:
            # 主要是数字
            val_str = str(sample_data[0])
            try:
                num_val = float(val_str)
                if num_val < 1000 and num_val > 0:
                    # 可能是数量或价格
                    if num_val < 10:
                        scores['price'] = 0.6  # 小数字可能是价格
                    scores['quantity'] = 0.5
            except:
                pass

            # 可能是序号 - 需要满足：数值较小且可能是连续递增的
            if all(re.match(r'^\d{1,4}$', str(v)) for v in sample_data[:3]):
                try:
                    nums = [int(float(v)) for v in sample_data[:5]]
                    is_sequential = all(nums[i] == nums[0] + i for i in range(len(nums)))
                    if is_sequential and nums[0] >= 1 and nums[-1] <= 100:
                        scores['seq'] = 0.8
                    elif max(nums) < 100:  # 小数字可能是序号
                        scores['seq'] = 0.4
                except:
                    pass

        if chinese_count / total > 0.5:
            # 含中文，可能是名称
            scores['name'] = 0.5

        return scores

    def _detect_data_start(self):
        """识别数据起始行"""
        # 从表头后开始找第一个有效数据行
        self.data_start_row = self.header_start_row + self.header_rows

        for idx in range(self.header_start_row + self.header_rows, len(self.df)):
            row = self.df.iloc[idx]
            non_empty = [v for v in row.values if pd.notna(v) and str(v).strip()]

            # 如果这行有足够多的非空值，认为是数据行
            if len(non_empty) >= 3:
                self.data_start_row = idx
                break

        print(f"数据起始行: {self.data_start_row}")

    def _extract_preview(self) -> List[Dict]:
        """提取预览数据"""
        preview = []
        for idx in range(self.data_start_row, min(self.data_start_row + 5, len(self.df))):
            row_data = {}
            used_types = set()  # 跟踪已使用的类型，避免覆盖

            for col_idx in range(len(self.df.columns)):
                col_mapping = self.column_mapping.get(col_idx, {})
                col_type = col_mapping.get('detected_type', '') or f'col_{col_idx}'
                val = self.df.iloc[idx, col_idx]
                # 确保值可序列化
                if pd.isna(val):
                    val_str = ''
                elif isinstance(val, float):
                    if val != val:  # NaN check
                        val_str = ''
                    else:
                        val_str = val
                else:
                    val_str = val

                # 对于已识别的类型，使用第一个匹配的列（避免覆盖）
                if col_type not in used_types:
                    row_data[col_type] = val_str
                    used_types.add(col_type)
                else:
                    # 如果类型已存在，添加带列号后缀
                    row_data[f'{col_type}_col{col_idx}'] = val_str

                row_data[f'original_col_{col_idx}'] = val_str
            preview.append(row_data)
        return preview

    def _get_raw_headers(self) -> List[str]:
        """获取原始表头列表"""
        headers = []
        header_end_row = min(self.header_start_row + self.header_rows, len(self.df))
        for col_idx in range(len(self.df.columns)):
            texts = []
            for row_idx in range(self.header_start_row, header_end_row):
                val = self.df.iloc[row_idx, col_idx]
                if pd.notna(val) and str(val).strip():
                    texts.append(str(val).strip())
            headers.append(' '.join(texts) if texts else f'列{col_idx + 1}')
        return headers

    def get_parsed_items(self, confirmed_mapping: Dict[int, str] = None) -> List[Dict]:
        """
        根据确认的映射关系提取报价项

        Args:
            confirmed_mapping: 用户确认的列映射 {列索引: 列类型}

        Returns:
            报价项列表
        """
        if confirmed_mapping is None:
            confirmed_mapping = {
                col_idx: mapping.get('detected_type')
                for col_idx, mapping in self.column_mapping.items()
                if mapping.get('detected_type')
            }

        # 对映射进行分组，每个类型取第一个非空值
        # 按列索引排序，确保前面的列优先
        type_columns = {}  # {类型: [列索引列表]}
        for col_idx, col_type in sorted(confirmed_mapping.items()):
            if col_type:
                if col_type not in type_columns:
                    type_columns[col_type] = []
                type_columns[col_type].append(col_idx)

        items = []
        for idx in range(self.data_start_row, len(self.df)):
            row = self.df.iloc[idx]

            # 检查是否为有效数据行
            non_empty = [v for v in row.values if pd.notna(v) and str(v).strip()]
            if len(non_empty) < 2:
                continue

            item = {'row_index': idx}

            # 根据映射提取数据，每个类型取第一个非空值
            for col_type, col_indices in type_columns.items():
                for col_idx in col_indices:
                    if col_idx < len(row.values):
                        val = row.values[col_idx]
                        if pd.notna(val) and str(val).strip():
                            item[col_type] = val
                            break  # 找到第一个非空值就停止
                # 如果所有列都为空，设置为空字符串
                if col_type not in item:
                    item[col_type] = ''

            # 确保至少有名称
            if item.get('name') and str(item['name']).strip():
                items.append(item)

        print(f"解析到 {len(items)} 个报价项")
        return self.normalize_items(items)