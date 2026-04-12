# -*- coding: utf-8 -*-
"""
Excel处理模块
功能：报价单解析、商品库导入、报价单导出
"""

import os
import math
import pandas as pd
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import List, Dict, Any, Optional
import json
from openpyxl import load_workbook, Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter

from utils.image_handler import ProductImageHandler


class ExcelHandler:
    """Excel处理类"""

    def __init__(self):
        pass

    def parse_quote(self, file) -> List[Dict]:
        """
        解析报价单

        Args:
            file: 上传的文件对象

        Returns:
            报价项列表
        """
        # 读取Excel或CSV文件
        try:
            if hasattr(file, 'filename') and file.filename.lower().endswith('.csv'):
                df = pd.read_csv(file, encoding='utf-8-sig', header=None)
            else:
                df = pd.read_excel(file, engine='xlrd' if file.filename.endswith('.xls') else 'openpyxl', header=None)
        except Exception as e:
            # 尝试另一种引擎
            try:
                df = pd.read_excel(file, header=None)
            except Exception as e2:
                raise Exception(f"无法读取文件: {str(e2)}")

        print(f"=== 报价单解析 ===")
        print(f"总行数: {len(df)}, 总列数: {len(df.columns)}")

        items = []

        # 遍历所有行，寻找数据行
        for idx, row in df.iterrows():
            # 获取所有值（包括空值，保留位置）
            row_values = list(row.values)

            # 跳过表头行（包含关键词的行）
            row_str = str([v for v in row_values if pd.notna(v)])
            if any(keyword in row_str for keyword in ['物资', '计量单位', '预算单价', '名称', '规格', '详细报价项', '十二']):
                print(f"跳过表头行 {idx}")
                continue

            # 跳过空行
            non_empty = [v for v in row_values if pd.notna(v) and str(v).strip()]
            if not non_empty or len(non_empty) < 2:
                continue

            # 判断是否为数据行：第一列应该是序号（数字）
            first_val = row_values[0]
            try:
                seq_num = float(first_val)
                if seq_num < 1 or seq_num > 1000:
                    continue
            except (ValueError, TypeError):
                continue

            # 按位置提取数据
            # 格式: 列0=序号, 列1=名称, 列2=单位, 列3=数量, 列4=预算单价, 后面=备注
            name = str(row_values[1]) if len(row_values) > 1 and pd.notna(row_values[1]) else ''
            unit = str(row_values[2]) if len(row_values) > 2 and pd.notna(row_values[2]) else ''
            quantity = row_values[3] if len(row_values) > 3 and pd.notna(row_values[3]) else ''

            # 预算单价 - 必须是数字
            budget_price = ''
            if len(row_values) > 4 and pd.notna(row_values[4]):
                try:
                    price_val = float(row_values[4])
                    budget_price = price_val
                except (ValueError, TypeError):
                    # 不是数字，可能是备注提前了
                    pass

            # 备注在最后一列（通常是倒数第1或第2列）
            remark = ''
            for i in range(len(row_values) - 1, 4, -1):
                if pd.notna(row_values[i]):
                    val_str = str(row_values[i])
                    # 备注通常包含这些关键词或较长
                    if 'GB' in val_str or '符合' in val_str or '标准' in val_str or len(val_str) > 15:
                        remark = val_str
                        break

            # 过滤无效数据
            if name and name not in ['物资', '名称', 'NaN', 'nan']:
                item = {
                    'seq': int(float(first_val)),
                    'name': name,
                    'unit': unit,
                    'quantity': quantity,
                    'budget_price': budget_price,
                    'spec': '',
                    'remark': remark,
                    'row_index': idx
                }
                items.append(item)
                print(f"解析第{item['seq']}项: {name}, 数量:{quantity}{unit}, 预算:{budget_price}")

        print(f"=== 共解析到 {len(items)} 个报价项 ===")

        if len(items) == 0:
            raise Exception("未能解析出任何报价项，请检查Excel格式。报价单应该包含：序号、名称、单位、数量等列")

        return items

    def export_quote(self, results: List[Dict], output_dir: str,
                     price_adjustment: Dict = None, export_format: str = 'standard',
                     price_type: str = 'market', customer_name: str = '',
                     template_definition: Dict = None) -> str:
        """
        导出报价单

        Args:
            results: 匹配结果列表
            output_dir: 输出目录
            price_adjustment: 价格调整配置 {type, value, scope}
            export_format: 导出格式 (standard/internal/statement/mall_quote)
            price_type: 价格类型 (market/adjusted/cost)
            customer_name: 客户名称
            template_definition: 导出模板定义

        Returns:
            输出文件路径
        """
        if export_format == 'mall_quote':
            return self.export_mall_document_template(
                results,
                output_dir,
                price_adjustment=price_adjustment,
                price_type=price_type,
                customer_name=customer_name,
                template_definition=template_definition or {}
            )

        if export_format == 'dropdown':
            return self.export_quote_with_dropdown(
                results,
                output_dir,
                customer_name=customer_name
            )


        def get_adjusted_price(original_price, is_matched, adjustment):
            """计算调整后的价格"""
            if not adjustment or not original_price or original_price <= 0:
                return original_price

            if adjustment.get('scope') == 'matched' and not is_matched:
                return original_price

            adj_type = adjustment.get('type', '')
            value = adjustment.get('value', 0)

            if adj_type == 'markup':
                return original_price * (1 + value / 100)
            elif adj_type == 'markdown':
                return original_price * (1 - value / 100)
            elif adj_type == 'fixed_markup':
                return original_price + value
            elif adj_type == 'fixed_markdown':
                return max(0, original_price - value)

            return original_price

        def get_price(product, price_t, adjustment, is_matched):
            """根据价格类型获取价格"""
            market_price = float(product.get('market_price', 0) or 0)
            cost_price = float(product.get('cost_price', 0) or 0)

            if price_t == 'cost':
                return cost_price
            elif price_t == 'adjusted' and adjustment:
                return get_adjusted_price(market_price, is_matched, adjustment)
            else:
                return market_price

        # 根据格式选择列
        if export_format == 'standard':
            # 标准报价单（给客户）
            columns = {
                '序号': lambda r, i: i + 1,
                '产品名称': lambda r, i: r.get('query_item', {}).get('name', ''),
                '需求数量': lambda r, i: r.get('query_item', {}).get('quantity', ''),
                '单位': lambda r, i: r.get('query_item', {}).get('unit', ''),
                '规格要求': lambda r, i: r.get('query_item', {}).get('spec', ''),
                '需求备注': lambda r, i: r.get('query_item', {}).get('remark', '') or r.get('query_item', {}).get('color', ''),
                '商品编码': lambda r, i: r.get('selected_product', {}).get('product', {}).get('code', '') if r.get('action') == 'select' else '',
                '商品名称': lambda r, i: r.get('selected_product', {}).get('product', {}).get('name', '') if r.get('action') == 'select' else '',
                '单价': lambda r, i: self._get_export_price(r, price_type, price_adjustment),
                '总价': lambda r, i: self._get_total_price(r, price_type, price_adjustment),
                '品牌': lambda r, i: r.get('selected_product', {}).get('product', {}).get('brand', '') if r.get('action') == 'select' else '',
                '匹配状态': lambda r, i: '✅ 已匹配' if r.get('action') == 'select' else ('❌ 无匹配' if r.get('action') == 'no_match' else '⏳ 待确认')
            }
            format_name = '标准报价单'

        elif export_format == 'internal':
            # 内部报价单（含成本价、利润）
            columns = {
                '序号': lambda r, i: i + 1,
                '产品名称': lambda r, i: r.get('query_item', {}).get('name', ''),
                '需求数量': lambda r, i: r.get('query_item', {}).get('quantity', ''),
                '单位': lambda r, i: r.get('query_item', {}).get('unit', ''),
                '规格要求': lambda r, i: r.get('query_item', {}).get('spec', ''),
                '需求备注': lambda r, i: r.get('query_item', {}).get('remark', '') or r.get('query_item', {}).get('color', ''),
                '预算单价': lambda r, i: r.get('query_item', {}).get('price', ''),
                '市场价': lambda r, i: r.get('selected_product', {}).get('product', {}).get('market_price', '') if r.get('action') == 'select' else '',
                '成本价': lambda r, i: r.get('selected_product', {}).get('product', {}).get('cost_price', '') if r.get('action') == 'select' else '',
                '报价单价': lambda r, i: self._get_export_price(r, price_type, price_adjustment),
                '利润': lambda r, i: self._get_profit(r, price_type, price_adjustment),
                '利润率': lambda r, i: self._get_profit_margin(r, price_type, price_adjustment),
                '总价': lambda r, i: self._get_total_price(r, price_type, price_adjustment),
                '供应商': lambda r, i: r.get('selected_product', {}).get('product', {}).get('supplier', '') if r.get('action') == 'select' else '',
                '匹配状态': lambda r, i: '✅ 已匹配' if r.get('action') == 'select' else ('❌ 无匹配' if r.get('action') == 'no_match' else '⏳ 待确认')
            }
            format_name = '内部报价单'

        else:  # statement
            # 对账单格式
            columns = {
                '序号': lambda r, i: i + 1,
                '商品名称': lambda r, i: r.get('selected_product', {}).get('product', {}).get('name', '') if r.get('action') == 'select' else r.get('query_item', {}).get('name', ''),
                '数量': lambda r, i: r.get('query_item', {}).get('quantity', ''),
                '单位': lambda r, i: r.get('query_item', {}).get('unit', ''),
                '单价': lambda r, i: self._get_export_price(r, price_type, price_adjustment),
                '金额': lambda r, i: self._get_total_price(r, price_type, price_adjustment),
                '供应商': lambda r, i: r.get('selected_product', {}).get('product', {}).get('supplier', '') if r.get('action') == 'select' else '',
                '备注': lambda r, i: r.get('query_item', {}).get('remark', '') or r.get('query_item', {}).get('color', '')
            }
            format_name = '对账单'

        # 准备导出数据
        export_data = []
        row_status = []  # 记录每行的状态
        for idx, result in enumerate(results):
            row = {}
            for col_name, getter in columns.items():
                row[col_name] = getter(result, idx)
            export_data.append(row)

            # 记录状态
            action = result.get('action', '')
            confirmed = result.get('confirmed', False)
            if action == 'select' and confirmed:
                row_status.append('matched')
            elif action in ['no_match', 'ask_boss']:
                row_status.append('nomatch')
            else:
                row_status.append('pending')

        # 创建DataFrame
        df = pd.DataFrame(export_data)

        # 生成文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        customer_suffix = f'_{customer_name}' if customer_name else ''
        filename = f'{format_name}{customer_suffix}_{timestamp}.xlsx'
        filepath = os.path.join(output_dir, filename)

        # 导出Excel
        df.to_excel(filepath, index=False, engine='openpyxl')

        # 添加样式（颜色区分状态）
        self._apply_export_styles(filepath, row_status)

        return filepath

    def _apply_export_styles(self, filepath: str, row_status: List[str]):
        """
        为导出的Excel添加样式

        Args:
            filepath: Excel文件路径
            row_status: 每行的状态列表
        """
        try:
            wb = load_workbook(filepath)
            ws = wb.active

            # 定义样式
            # 已匹配 - 浅绿色背景
            matched_fill = PatternFill(start_color='C6EFCE', end_color='C6EFCE', fill_type='solid')
            matched_font = Font(color='006100')

            # 待确认 - 浅黄色背景
            pending_fill = PatternFill(start_color='FFEB9C', end_color='FFEB9C', fill_type='solid')
            pending_font = Font(color='9C5700')

            # 无匹配 - 浅红色背景
            nomatch_fill = PatternFill(start_color='FFC7CE', end_color='FFC7CE', fill_type='solid')
            nomatch_font = Font(color='9C0006')

            # 表头样式
            header_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
            header_font = Font(bold=True, color='FFFFFF')
            header_alignment = Alignment(horizontal='center', vertical='center')

            # 边框
            thin_border = Border(
                left=Side(style='thin'),
                right=Side(style='thin'),
                top=Side(style='thin'),
                bottom=Side(style='thin')
            )

            # 设置表头样式
            for cell in ws[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = header_alignment
                cell.border = thin_border

            # 设置数据行样式
            for row_idx, status in enumerate(row_status, start=2):  # 从第2行开始（跳过表头）
                row = ws[row_idx]
                if status == 'matched':
                    fill, font = matched_fill, matched_font
                elif status == 'pending':
                    fill, font = pending_fill, pending_font
                else:  # nomatch
                    fill, font = nomatch_fill, nomatch_font

                for cell in row:
                    cell.fill = fill
                    cell.font = font
                    cell.border = thin_border

            # 自动调整列宽
            for column in ws.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if cell.value:
                            cell_length = len(str(cell.value))
                            # 中文字符算2个长度
                            chinese_count = sum(1 for c in str(cell.value) if '\u4e00' <= c <= '\u9fff')
                            cell_length = cell_length + chinese_count
                            if cell_length > max_length:
                                max_length = cell_length
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)  # 最大50
                ws.column_dimensions[column_letter].width = adjusted_width

            wb.save(filepath)
        except Exception as e:
            print(f"添加样式失败: {e}")
            # 样式失败不影响导出功能

    def _get_export_price(self, result, price_type, price_adjustment):
        """获取导出价格"""
        if result.get('action') != 'select':
            return ''

        product = result.get('selected_product', {}).get('product', {})
        market_price = float(product.get('market_price', 0) or 0)
        cost_price = float(product.get('cost_price', 0) or 0)

        if price_type == 'cost':
            return cost_price if cost_price > 0 else ''
        elif price_type == 'adjusted' and price_adjustment:
            # 计算调整后价格
            adj_type = price_adjustment.get('type', '')
            value = price_adjustment.get('value', 0)

            if adj_type == 'markup':
                return round(market_price * (1 + value / 100), 2)
            elif adj_type == 'markdown':
                return round(market_price * (1 - value / 100), 2)
            elif adj_type == 'fixed_markup':
                return round(market_price + value, 2)
            elif adj_type == 'fixed_markdown':
                return round(max(0, market_price - value), 2)

        return market_price if market_price > 0 else ''

    def _get_total_price(self, result, price_type, price_adjustment):
        """计算总价"""
        if result.get('action') != 'select':
            return ''

        try:
            qty = float(result.get('query_item', {}).get('quantity', 0))
            price = self._get_export_price(result, price_type, price_adjustment)
            if price:
                return round(qty * float(price), 2)
        except:
            pass
        return ''

    def _get_profit(self, result, price_type, price_adjustment):
        """计算利润"""
        if result.get('action') != 'select':
            return ''

        product = result.get('selected_product', {}).get('product', {})
        cost_price = float(product.get('cost_price', 0) or 0)
        sell_price = self._get_export_price(result, price_type, price_adjustment)

        if cost_price > 0 and sell_price:
            return round(float(sell_price) - cost_price, 2)
        return ''

    def _get_profit_margin(self, result, price_type, price_adjustment):
        """计算利润率"""
        if result.get('action') != 'select':
            return ''

        product = result.get('selected_product', {}).get('product', {})
        cost_price = float(product.get('cost_price', 0) or 0)
        profit = self._get_profit(result, price_type, price_adjustment)

        if cost_price > 0 and profit != '':
            margin = float(profit) / cost_price * 100
            return f'{round(margin, 1)}%'
        return ''

    def _safe_float_value(self, value, default=0.0):
        """安全转换为浮点数"""
        if value is None:
            return default
        if isinstance(value, (int, float)):
            try:
                number = float(value)
                if math.isnan(number) or math.isinf(number):
                    return default
                return number
            except Exception:
                return default

        text = str(value).strip().replace(',', '')
        if not text or text.lower() in {'nan', 'none', 'null', '--', '-'}:
            return default

        try:
            number = float(text)
            if math.isnan(number) or math.isinf(number):
                return default
            return number
        except Exception:
            return default

    def _safe_text_value(self, value, default=''):
        """安全转换为文本"""
        if value is None:
            return default
        if isinstance(value, float) and math.isnan(value):
            return default
        text = str(value).strip()
        if not text or text.lower() in {'nan', 'none', 'null'}:
            return default
        return text

    def _round_currency(self, value) -> float:
        """统一货币四舍五入"""
        amount = Decimal(str(self._safe_float_value(value, 0.0)))
        return float(amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

    def _format_quantity_value(self, value):
        """格式化数量展示"""
        number = self._safe_float_value(value, None)
        if number is None:
            return self._safe_text_value(value)
        if float(number).is_integer():
            return int(number)
        return number

    def _convert_amount_to_chinese(self, amount) -> str:
        """将金额转换为中文大写"""
        digits = '零壹贰叁肆伍陆柒捌玖'
        small_units = ['', '拾', '佰', '仟']
        large_units = ['', '万', '亿', '兆']
        decimals = ['角', '分']

        def section_to_chinese(section: int) -> str:
            section_text = ''
            unit_index = 0
            zero_pending = False
            while section > 0:
                digit = section % 10
                if digit == 0:
                    if section_text:
                        zero_pending = True
                else:
                    prefix = digits[digit] + small_units[unit_index]
                    if zero_pending:
                        prefix = digits[0] + prefix
                        zero_pending = False
                    section_text = prefix + section_text
                unit_index += 1
                section //= 10
            return section_text

        amount_decimal = Decimal(str(self._round_currency(amount))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if amount_decimal == 0:
            return '零元整'

        integer_part = int(amount_decimal)
        decimal_part = int((amount_decimal - integer_part) * 100)

        if integer_part == 0:
            integer_text = digits[0]
        else:
            integer_text = ''
            unit_pos = 0
            zero_between = False
            while integer_part > 0:
                section = integer_part % 10000
                if section:
                    section_text = section_to_chinese(section) + large_units[unit_pos]
                    if zero_between:
                        integer_text = digits[0] + integer_text
                    integer_text = section_text + integer_text
                    zero_between = section < 1000
                else:
                    if integer_text:
                        zero_between = True
                integer_part //= 10000
                unit_pos += 1

        decimal_text = ''
        jiao = decimal_part // 10
        fen = decimal_part % 10
        if jiao:
            decimal_text += digits[jiao] + decimals[0]
        if fen:
            if not jiao:
                decimal_text += digits[0]
            decimal_text += digits[fen] + decimals[1]

        return f"{integer_text}元{'整' if not decimal_text else decimal_text}"

    def _resolve_template_base_dir(self) -> Optional[Path]:
        """定位商城模板目录"""
        project_root = Path(__file__).resolve().parents[1]
        candidates = [
            project_root / '导出模板',
            project_root.parent / '模版订单' / '自定义订单模板示例和制作指南' / '自定义订单模板示例和制作指南' / '导出模板',
            project_root.parent.parent / '模版订单' / '自定义订单模板示例和制作指南' / '自定义订单模板示例和制作指南' / '导出模板'
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_dir():
                return candidate
        return None

    def _get_mall_template_path(self, doc_type: str = 'quote', template_variant: str = 'classic') -> Optional[Path]:
        """获取商城单据模板路径"""
        base_dir = self._resolve_template_base_dir()
        if not base_dir:
            return None

        template_candidates = {
            ('quote', 'classic'): ['报价单模板示例.xlsx', '报价单模板示例.xls'],
            ('quote', 'standard'): ['报价单模板示例.xlsx', '报价单模板示例.xls'],
            ('order', 'standard'): ['订货单模板示例02.xlsx', '订货单模板示例01.xls'],
            ('order', 'qrcode'): ['订货单模板示例03(含支付二维码).xls'],
            ('order', 'with_images'): ['订货单模板示例04(含商品明细图片).xls', '吴总订货单模板(含商品图片).xls'],
            ('delivery', 'standard'): ['发货单模板示例02.xls', '发货单模板示例01.xls'],
            ('delivery', 'with_images'): ['发货单模板示例03(含商品明细图片).xls'],
            ('purchase', 'standard'): ['采购订单模板示例.xls', '采购订单模板示例02(含商品明细图片).xls'],
            ('supplier_order', 'standard'): ['供应商订单模板示例.xls'],
            ('return', 'standard'): ['退货单模板示例01.xls', '退货单模板示例02.xls'],
            ('purchase_return', 'standard'): ['采购退货订单模板示例.xls'],
            ('inbound', 'standard'): ['入库单模板示例.xls'],
            ('inbound', 'with_images'): ['入库单模板示例(含商品明细图片).xls'],
            ('merge_outbound', 'standard'): ['合并出库订货单模板示例.xls', '合并打印单模板.xls'],
            ('order_items', 'standard'): ['订单商品明细模板示例.xlsx']
        }

        candidate_names = (
            template_candidates.get((doc_type, template_variant))
            or template_candidates.get((doc_type, 'standard'))
            or template_candidates.get((doc_type, 'classic'))
            or template_candidates.get(('quote', 'classic'))
            or []
        )
        for name in candidate_names:
            candidate = base_dir / name
            if candidate.exists():
                return candidate
        return None

    def _get_mall_quote_template_path(self) -> Optional[Path]:
        """获取商城报价单模板路径"""
        return self._get_mall_template_path('quote', 'classic')

    def _compute_price_for_export(self, result, price_type, price_adjustment):
        """计算导出单价"""
        price = self._get_export_price(result, price_type, price_adjustment)
        if price == '':
            return None
        return self._round_currency(price)

    def _get_mall_document_title(self, doc_type: str) -> str:
        titles = {
            'quote': '报价单',
            'order': '订货单',
            'delivery': '发货单',
            'purchase': '采购单',
            'supplier_order': '供应商订单',
            'return': '退货单',
            'purchase_return': '采购退货单',
            'inbound': '入库单',
            'merge_outbound': '合并出库单',
            'order_items': '订单商品明细'
        }
        return titles.get(doc_type, '商城单据')

    def _get_mall_document_number_prefix(self, doc_type: str) -> str:
        prefixes = {
            'quote': 'BJ',
            'order': 'DH',
            'delivery': 'FH',
            'purchase': 'CG',
            'supplier_order': 'GY',
            'return': 'TH',
            'purchase_return': 'CT',
            'inbound': 'RK',
            'merge_outbound': 'HB',
            'order_items': 'MX'
        }
        return prefixes.get(doc_type, 'DJ')

    def _safe_filename_segment(self, value, default='') -> str:
        text = self._safe_text_value(value, default)
        if not text:
            return ''
        invalid_chars = '<>:"/\\|?*'
        sanitized = ''.join('_' if ch in invalid_chars else ch for ch in text)
        return sanitized.strip(' ._')

    def _build_mall_quote_items(self, results: List[Dict], price_adjustment: Dict = None,
                                price_type: str = 'market') -> List[Dict[str, Any]]:
        """构建商城单据明细"""
        items = []
        for result in results:
            if result.get('action') != 'select':
                continue

            query_item = result.get('query_item', {}) or {}
            product = result.get('selected_product', {}).get('product', {}) or {}
            quantity_value = self._format_quantity_value(query_item.get('quantity', ''))
            quantity_number = self._safe_float_value(query_item.get('quantity', ''), 0.0)
            unit_price = self._compute_price_for_export(result, price_type, price_adjustment)
            sum_price = self._round_currency(quantity_number * unit_price) if unit_price is not None and quantity_number > 0 else None
            proxy_images = ProductImageHandler.get_proxy_images(product, max_images=1)
            first_image = proxy_images[0] if proxy_images else {}
            product_image_url = self._safe_text_value(
                first_image.get('source_url') or first_image.get('url') or first_image.get('proxy_url')
            )

            items.append({
                'index': len(items) + 1,
                'product_code': self._safe_text_value(product.get('code')),
                'product_brand': self._safe_text_value(product.get('brand')),
                'product_name': self._safe_text_value(product.get('name') or query_item.get('name')),
                'query_name': self._safe_text_value(query_item.get('name')),
                'product_spec_name': self._safe_text_value(product.get('model') or query_item.get('spec')),
                'unit_name': self._safe_text_value(product.get('unit') or query_item.get('unit')),
                'order_count': quantity_value,
                'quantity_number': quantity_number,
                'unit_price': unit_price,
                'sum_price': sum_price,
                'product_remark': self._safe_text_value(query_item.get('remark') or query_item.get('color')),
                'supplier_name': self._safe_text_value(product.get('supplier')),
                'product_image_url': product_image_url
            })
        return items

    def _build_mall_document_context(self, results: List[Dict], price_adjustment: Dict = None,
                                     price_type: str = 'market', customer_name: str = '',
                                     template_definition: Dict = None) -> Dict[str, Any]:
        """构建商城单据上下文"""
        template_definition = template_definition or {}
        doc_type = self._safe_text_value(template_definition.get('doc_type'), 'quote') or 'quote'
        default_variant = 'classic' if doc_type == 'quote' else 'standard'
        template_variant = self._safe_text_value(template_definition.get('template_variant'), default_variant) or default_variant
        create_time = datetime.now()
        items = self._build_mall_quote_items(results, price_adjustment=price_adjustment, price_type=price_type)
        total_amount = self._round_currency(sum(item['sum_price'] or 0 for item in items))
        template_path = self._get_mall_template_path(doc_type, template_variant)
        document_title = self._get_mall_document_title(doc_type)
        document_no = f"{self._get_mall_document_number_prefix(doc_type)}{create_time.strftime('%Y%m%d%H%M%S')}"
        supplier_name = next((item['supplier_name'] for item in items if item.get('supplier_name')), '待补充供应商')
        safe_customer_name = self._safe_text_value(customer_name, '未填写客户名称')
        show_images = template_variant == 'with_images'
        reference_template = template_path.name if template_path else f'{document_title}模板示例'

        return {
            'document_no': document_no,
            'quotation_no': document_no,
            'create_time': create_time,
            'create_time_display': create_time.strftime('%Y-%m-%d %H:%M'),
            'create_date_display': create_time.strftime('%Y-%m-%d'),
            'document_title': document_title,
            'doc_type': doc_type,
            'template_variant': template_variant,
            'template_label': self._safe_text_value(template_definition.get('label'), document_title),
            'customer_name': safe_customer_name,
            'creater_name': '一键报价系统',
            'items': items,
            'all_sum_price': total_amount,
            'amount_to_chinese': self._convert_amount_to_chinese(total_amount),
            'template_reference': reference_template,
            'template_path': str(template_path) if template_path else '',
            'supplier_name': supplier_name,
            'receiver_info': f'{safe_customer_name} / 待补充收货信息',
            'contact_name': '待补充联系人',
            'contact_phone': '待补充联系电话',
            'order_note': '由已确认报价结果生成，可按实际单据继续补充页头信息。',
            'logistics_company': '待补充物流公司',
            'logistics_no': f'WL{create_time.strftime("%m%d%H%M%S")}',
            'delivery_date': create_time.strftime('%Y-%m-%d'),
            'warehouse_name': '默认仓库',
            'purchase_eta': create_time.strftime('%Y-%m-%d'),
            'related_order_no': f'ORD{create_time.strftime("%m%d%H%M%S")}',
            'related_purchase_no': f'CG{create_time.strftime("%m%d%H%M%S")}',
            'source_documents': f'报价确认结果 / {document_no}',
            'return_reason': '待补充退货原因',
            'show_images': show_images,
            'qrcode_note': '当前二维码版先输出二维码占位说明，后续可继续接入真实二维码图片。' if template_variant == 'qrcode' else '',
            'requires_extra_fields': template_definition.get('requires_extra_fields', []) or []
        }

    def _build_mall_document_export_config(self, context: Dict[str, Any]) -> Dict[str, Any]:
        doc_type = context.get('doc_type', 'quote')
        show_images = bool(context.get('show_images'))
        document_title = context.get('document_title') or self._get_mall_document_title(doc_type)

        configs = {
            'quote': {
                'sheet_title': '报价单',
                'filename_prefix': '商城模板报价单',
                'info_rows': [
                    [f"报价单号：{context['document_no']}", f"报价时间：{context['create_time_display']}", f"报价员：{context['creater_name']}"],
                    [f"客户名称：{context['customer_name']}", '单据类型：商城模板报价单', f"参考模板：{context['template_reference']}"]
                ],
                'notes': ['说明：本报价单由一键报价系统按商城模板规则生成，可继续扩展为订货单、发货单等模板。'],
                'columns': [
                    {'header': '序号', 'key': 'index', 'width': 8, 'align': 'center'},
                    {'header': '品牌', 'key': 'product_brand', 'width': 14, 'align': 'left'},
                    {'header': '商品名称', 'key': 'product_name', 'width': 26, 'align': 'left'},
                    {'header': '规格', 'key': 'product_spec_name', 'width': 18, 'align': 'left'},
                    {'header': '数量', 'key': 'order_count', 'width': 10, 'align': 'center'},
                    {'header': '单价', 'key': 'unit_price', 'width': 12, 'align': 'center', 'currency': True},
                    {'header': '单位', 'key': 'unit_name', 'width': 10, 'align': 'center'},
                    {'header': '小计', 'key': 'sum_price', 'width': 14, 'align': 'center', 'currency': True},
                    {'header': '备注', 'key': 'product_remark', 'width': 24, 'align': 'left'}
                ]
            },
            'order': {
                'sheet_title': '订货单',
                'filename_prefix': '商城订货单',
                'info_rows': [
                    [f"订货单号：{context['document_no']}", f"下单时间：{context['create_time_display']}", f"客户名称：{context['customer_name']}"],
                    [f"联系人：{context['contact_name']}", f"联系电话：{context['contact_phone']}", f"收货信息：{context['receiver_info']}"],
                    [f"订单备注：{context['order_note']}", f"模板版本：{context['template_label']}", f"参考模板：{context['template_reference']}"]
                ],
                'notes': [note for note in [context.get('qrcode_note', ''), '说明：订货单按当前已确认匹配结果生成，页头缺失字段可在导出后补录。'] if note],
                'columns': [
                    {'header': '序号', 'key': 'index', 'width': 8, 'align': 'center'},
                    {'header': '商品编码', 'key': 'product_code', 'width': 16, 'align': 'left'},
                    {'header': '商品名称', 'key': 'product_name', 'width': 24, 'align': 'left'},
                    {'header': '规格', 'key': 'product_spec_name', 'width': 18, 'align': 'left'},
                    {'header': '订货数量', 'key': 'order_count', 'width': 10, 'align': 'center'},
                    {'header': '单价', 'key': 'unit_price', 'width': 12, 'align': 'center', 'currency': True},
                    {'header': '单位', 'key': 'unit_name', 'width': 10, 'align': 'center'},
                    {'header': '小计', 'key': 'sum_price', 'width': 14, 'align': 'center', 'currency': True},
                    {'header': '备注', 'key': 'product_remark', 'width': 24, 'align': 'left'}
                ]
            },
            'delivery': {
                'sheet_title': '发货单',
                'filename_prefix': '商城发货单',
                'info_rows': [
                    [f"发货单号：{context['document_no']}", f"发货时间：{context['delivery_date']}", f"客户名称：{context['customer_name']}"],
                    [f"物流公司：{context['logistics_company']}", f"物流单号：{context['logistics_no']}", f"收货信息：{context['receiver_info']}"],
                    [f"仓库：{context['warehouse_name']}", f"模板版本：{context['template_label']}", f"参考模板：{context['template_reference']}"]
                ],
                'notes': ['说明：发货单重点承接物流与收货信息；当前缺失字段会保留可读占位。'],
                'columns': [
                    {'header': '序号', 'key': 'index', 'width': 8, 'align': 'center'},
                    {'header': '商品编码', 'key': 'product_code', 'width': 16, 'align': 'left'},
                    {'header': '商品名称', 'key': 'product_name', 'width': 24, 'align': 'left'},
                    {'header': '规格', 'key': 'product_spec_name', 'width': 18, 'align': 'left'},
                    {'header': '出库数量', 'key': 'order_count', 'width': 10, 'align': 'center'},
                    {'header': '单价', 'key': 'unit_price', 'width': 12, 'align': 'center', 'currency': True},
                    {'header': '单位', 'key': 'unit_name', 'width': 10, 'align': 'center'},
                    {'header': '小计', 'key': 'sum_price', 'width': 14, 'align': 'center', 'currency': True},
                    {'header': '备注', 'key': 'product_remark', 'width': 24, 'align': 'left'}
                ]
            },
            'purchase': {
                'sheet_title': '采购单',
                'filename_prefix': '商城采购单',
                'info_rows': [
                    [f"采购单号：{context['document_no']}", f"制单时间：{context['create_time_display']}", f"供应商：{context['supplier_name']}"],
                    [f"交期：{context['purchase_eta']}", f"仓库：{context['warehouse_name']}", f"参考模板：{context['template_reference']}"],
                    [f"客户来源：{context['customer_name']}", f"模板版本：{context['template_label']}", '价格口径：按当前导出价格类型生成']
                ],
                'notes': ['说明：采购单优先用于内部采购流转，建议选择成本价口径导出。'],
                'columns': [
                    {'header': '序号', 'key': 'index', 'width': 8, 'align': 'center'},
                    {'header': '供应商', 'key': 'supplier_name', 'width': 16, 'align': 'left'},
                    {'header': '商品编码', 'key': 'product_code', 'width': 16, 'align': 'left'},
                    {'header': '商品名称', 'key': 'product_name', 'width': 22, 'align': 'left'},
                    {'header': '规格', 'key': 'product_spec_name', 'width': 16, 'align': 'left'},
                    {'header': '采购数量', 'key': 'order_count', 'width': 10, 'align': 'center'},
                    {'header': '采购单价', 'key': 'unit_price', 'width': 12, 'align': 'center', 'currency': True},
                    {'header': '小计', 'key': 'sum_price', 'width': 14, 'align': 'center', 'currency': True},
                    {'header': '备注', 'key': 'product_remark', 'width': 22, 'align': 'left'}
                ]
            },
            'supplier_order': {
                'sheet_title': '供应商订单',
                'filename_prefix': '商城供应商订单',
                'info_rows': [
                    [f"供应商订单号：{context['document_no']}", f"制单时间：{context['create_time_display']}", f"供应商：{context['supplier_name']}"],
                    [f"联系人：{context['contact_name']}", f"联系电话：{context['contact_phone']}", f"交期：{context['purchase_eta']}"],
                    [f"来源客户：{context['customer_name']}", f"模板版本：{context['template_label']}", f"参考模板：{context['template_reference']}"]
                ],
                'notes': ['说明：供应商订单用于外部协同，建议在导出后补充联系人与交付细节。'],
                'columns': [
                    {'header': '序号', 'key': 'index', 'width': 8, 'align': 'center'},
                    {'header': '商品编码', 'key': 'product_code', 'width': 16, 'align': 'left'},
                    {'header': '商品名称', 'key': 'product_name', 'width': 22, 'align': 'left'},
                    {'header': '规格', 'key': 'product_spec_name', 'width': 16, 'align': 'left'},
                    {'header': '数量', 'key': 'order_count', 'width': 10, 'align': 'center'},
                    {'header': '采购单价', 'key': 'unit_price', 'width': 12, 'align': 'center', 'currency': True},
                    {'header': '单位', 'key': 'unit_name', 'width': 10, 'align': 'center'},
                    {'header': '交期', 'value': lambda item: context['purchase_eta'], 'width': 12, 'align': 'center'},
                    {'header': '备注', 'key': 'product_remark', 'width': 22, 'align': 'left'}
                ]
            },
            'return': {
                'sheet_title': '退货单',
                'filename_prefix': '商城退货单',
                'info_rows': [
                    [f"退货单号：{context['document_no']}", f"退货时间：{context['create_time_display']}", f"客户名称：{context['customer_name']}"],
                    [f"关联订单号：{context['related_order_no']}", f"退货原因：{context['return_reason']}", f"参考模板：{context['template_reference']}"],
                    [f"收货信息：{context['receiver_info']}", f"模板版本：{context['template_label']}", '单据方向：销售退货']
                ],
                'notes': ['说明：退货单用于销售逆向流转，默认保留关联单号和退货原因占位。'],
                'columns': [
                    {'header': '序号', 'key': 'index', 'width': 8, 'align': 'center'},
                    {'header': '关联订单号', 'value': lambda item: context['related_order_no'], 'width': 16, 'align': 'left'},
                    {'header': '商品编码', 'key': 'product_code', 'width': 16, 'align': 'left'},
                    {'header': '商品名称', 'key': 'product_name', 'width': 22, 'align': 'left'},
                    {'header': '规格', 'key': 'product_spec_name', 'width': 16, 'align': 'left'},
                    {'header': '退货数量', 'key': 'order_count', 'width': 10, 'align': 'center'},
                    {'header': '单价', 'key': 'unit_price', 'width': 12, 'align': 'center', 'currency': True},
                    {'header': '退货原因', 'value': lambda item: context['return_reason'], 'width': 16, 'align': 'left'},
                    {'header': '备注', 'key': 'product_remark', 'width': 20, 'align': 'left'}
                ]
            },
            'purchase_return': {
                'sheet_title': '采购退货单',
                'filename_prefix': '商城采购退货单',
                'info_rows': [
                    [f"采购退货单号：{context['document_no']}", f"退货时间：{context['create_time_display']}", f"供应商：{context['supplier_name']}"],
                    [f"关联采购单号：{context['related_purchase_no']}", f"退货原因：{context['return_reason']}", f"参考模板：{context['template_reference']}"],
                    [f"仓库：{context['warehouse_name']}", f"模板版本：{context['template_label']}", '单据方向：采购退货']
                ],
                'notes': ['说明：采购退货单面向供应商逆向流转，建议导出后补充关联采购单号。'],
                'columns': [
                    {'header': '序号', 'key': 'index', 'width': 8, 'align': 'center'},
                    {'header': '供应商', 'key': 'supplier_name', 'width': 16, 'align': 'left'},
                    {'header': '商品编码', 'key': 'product_code', 'width': 16, 'align': 'left'},
                    {'header': '商品名称', 'key': 'product_name', 'width': 22, 'align': 'left'},
                    {'header': '规格', 'key': 'product_spec_name', 'width': 16, 'align': 'left'},
                    {'header': '退货数量', 'key': 'order_count', 'width': 10, 'align': 'center'},
                    {'header': '采购单价', 'key': 'unit_price', 'width': 12, 'align': 'center', 'currency': True},
                    {'header': '退货原因', 'value': lambda item: context['return_reason'], 'width': 16, 'align': 'left'},
                    {'header': '备注', 'key': 'product_remark', 'width': 20, 'align': 'left'}
                ]
            },
            'inbound': {
                'sheet_title': '入库单',
                'filename_prefix': '商城入库单',
                'info_rows': [
                    [f"入库单号：{context['document_no']}", f"入库时间：{context['create_time_display']}", f"仓库：{context['warehouse_name']}"],
                    [f"供应商：{context['supplier_name']}", f"收货负责人：{context['contact_name']}", f"参考模板：{context['template_reference']}"],
                    [f"来源单据：{context['source_documents']}", f"模板版本：{context['template_label']}", '单据方向：仓储入库']
                ],
                'notes': ['说明：入库单按当前商品明细展开，适合仓库验货与收货登记。'],
                'columns': [
                    {'header': '序号', 'key': 'index', 'width': 8, 'align': 'center'},
                    {'header': '商品编码', 'key': 'product_code', 'width': 16, 'align': 'left'},
                    {'header': '商品名称', 'key': 'product_name', 'width': 22, 'align': 'left'},
                    {'header': '规格', 'key': 'product_spec_name', 'width': 16, 'align': 'left'},
                    {'header': '入库数量', 'key': 'order_count', 'width': 10, 'align': 'center'},
                    {'header': '单价', 'key': 'unit_price', 'width': 12, 'align': 'center', 'currency': True},
                    {'header': '单位', 'key': 'unit_name', 'width': 10, 'align': 'center'},
                    {'header': '小计', 'key': 'sum_price', 'width': 14, 'align': 'center', 'currency': True},
                    {'header': '备注', 'key': 'product_remark', 'width': 20, 'align': 'left'}
                ]
            },
            'merge_outbound': {
                'sheet_title': '合并出库单',
                'filename_prefix': '商城合并出库单',
                'info_rows': [
                    [f"合并单号：{context['document_no']}", f"生成时间：{context['create_time_display']}", f"客户名称：{context['customer_name']}"],
                    [f"来源单据：{context['source_documents']}", f"收货信息：{context['receiver_info']}", f"参考模板：{context['template_reference']}"],
                    [f"仓库：{context['warehouse_name']}", f"模板版本：{context['template_label']}", '适用场景：批量打印 / 合单出库']
                ],
                'notes': ['说明：合并出库单用于同批次商品汇总出库，来源单据当前按统一占位输出。'],
                'columns': [
                    {'header': '序号', 'key': 'index', 'width': 8, 'align': 'center'},
                    {'header': '来源单据', 'value': lambda item: context['source_documents'], 'width': 18, 'align': 'left'},
                    {'header': '商品编码', 'key': 'product_code', 'width': 16, 'align': 'left'},
                    {'header': '商品名称', 'key': 'product_name', 'width': 22, 'align': 'left'},
                    {'header': '规格', 'key': 'product_spec_name', 'width': 16, 'align': 'left'},
                    {'header': '数量', 'key': 'order_count', 'width': 10, 'align': 'center'},
                    {'header': '单价', 'key': 'unit_price', 'width': 12, 'align': 'center', 'currency': True},
                    {'header': '小计', 'key': 'sum_price', 'width': 14, 'align': 'center', 'currency': True},
                    {'header': '备注', 'key': 'product_remark', 'width': 20, 'align': 'left'}
                ]
            },
            'order_items': {
                'sheet_title': '订单商品明细',
                'filename_prefix': '商城订单商品明细',
                'info_rows': [
                    [f"订单号：{context['related_order_no']}", f"导出时间：{context['create_time_display']}", f"客户名称：{context['customer_name']}"],
                    [f"来源单据：{context['source_documents']}", f"模板版本：{context['template_label']}", f"参考模板：{context['template_reference']}"]
                ],
                'notes': ['说明：订单商品明细聚焦逐行商品输出，适合运营整理或行级核对。'],
                'columns': [
                    {'header': '序号', 'key': 'index', 'width': 8, 'align': 'center'},
                    {'header': '订单号', 'value': lambda item: context['related_order_no'], 'width': 16, 'align': 'left'},
                    {'header': '商品编码', 'key': 'product_code', 'width': 16, 'align': 'left'},
                    {'header': '品牌', 'key': 'product_brand', 'width': 14, 'align': 'left'},
                    {'header': '商品名称', 'key': 'product_name', 'width': 22, 'align': 'left'},
                    {'header': '规格', 'key': 'product_spec_name', 'width': 16, 'align': 'left'},
                    {'header': '数量', 'key': 'order_count', 'width': 10, 'align': 'center'},
                    {'header': '单位', 'key': 'unit_name', 'width': 10, 'align': 'center'},
                    {'header': '单价', 'key': 'unit_price', 'width': 12, 'align': 'center', 'currency': True},
                    {'header': '小计', 'key': 'sum_price', 'width': 14, 'align': 'center', 'currency': True}
                ]
            }
        }

        config = dict(configs.get(doc_type, configs['quote']))
        config['title'] = document_title
        columns = list(config['columns'])
        if show_images:
            image_column = {'header': '商品图片', 'key': 'product_image_url', 'width': 26, 'align': 'left'}
            insert_after = 2 if doc_type in {'delivery', 'inbound'} else 1
            columns.insert(insert_after + 1, image_column)
        config['columns'] = columns
        return config

    def _write_grouped_info_row(self, ws, row_idx: int, values: List[str], total_columns: int,
                                font: Font, alignment: Alignment, border: Border):
        values = [self._safe_text_value(value) for value in values if self._safe_text_value(value)]
        if not values:
            return

        start_col = 1
        remaining_cols = total_columns
        remaining_values = len(values)
        for value in values:
            span = max(1, remaining_cols // remaining_values)
            end_col = start_col + span - 1
            if remaining_values == 1:
                end_col = total_columns
            if end_col > total_columns:
                end_col = total_columns
            if end_col > start_col:
                ws.merge_cells(start_row=row_idx, start_column=start_col, end_row=row_idx, end_column=end_col)
            cell = ws.cell(row=row_idx, column=start_col, value=value)
            cell.font = font
            cell.alignment = alignment
            for col_idx in range(start_col, end_col + 1):
                ws.cell(row=row_idx, column=col_idx).border = border
            start_col = end_col + 1
            remaining_cols = total_columns - end_col
            remaining_values -= 1
            if start_col > total_columns:
                break

    def _resolve_mall_column_value(self, item: Dict[str, Any], column: Dict[str, Any]):
        getter = column.get('value')
        if callable(getter):
            return getter(item)
        key = column.get('key', '')
        return item.get(key, '')

    def export_mall_document_template(self, results: List[Dict], output_dir: str,
                                      price_adjustment: Dict = None, price_type: str = 'market',
                                      customer_name: str = '', template_definition: Dict = None) -> str:
        """导出商城单据模板"""
        context = self._build_mall_document_context(
            results,
            price_adjustment=price_adjustment,
            price_type=price_type,
            customer_name=customer_name,
            template_definition=template_definition
        )

        if not context['items']:
            raise Exception('没有可导出的已匹配商品，请至少先确认 1 个匹配结果')

        config = self._build_mall_document_export_config(context)
        columns = config['columns']
        total_columns = len(columns)

        os.makedirs(output_dir, exist_ok=True)

        wb = Workbook()
        ws = wb.active
        ws.title = config['sheet_title'][:31]
        ws.sheet_view.showGridLines = False

        title_fill = PatternFill(start_color='D9EAF7', end_color='D9EAF7', fill_type='solid')
        section_fill = PatternFill(start_color='EAF2F8', end_color='EAF2F8', fill_type='solid')
        header_fill = PatternFill(start_color='5B9BD5', end_color='5B9BD5', fill_type='solid')
        white_font = Font(color='FFFFFF', bold=True)
        title_font = Font(size=16, bold=True)
        info_font = Font(size=10)
        total_font = Font(size=11, bold=True)
        note_font = Font(size=9, color='666666')
        center_alignment = Alignment(horizontal='center', vertical='center')
        left_alignment = Alignment(horizontal='left', vertical='center')
        wrap_alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
        thin_border = Border(
            left=Side(style='thin', color='B7C9D6'),
            right=Side(style='thin', color='B7C9D6'),
            top=Side(style='thin', color='B7C9D6'),
            bottom=Side(style='thin', color='B7C9D6')
        )

        for index, column in enumerate(columns, 1):
            ws.column_dimensions[get_column_letter(index)].width = column.get('width', 14)

        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_columns)
        ws.cell(row=1, column=1, value=config['title'])
        ws.cell(row=1, column=1).font = title_font
        ws.cell(row=1, column=1).alignment = center_alignment
        ws.cell(row=1, column=1).fill = title_fill
        for col_idx in range(1, total_columns + 1):
            ws.cell(row=1, column=col_idx).border = thin_border
        ws.row_dimensions[1].height = 28

        current_row = 2
        for info_values in config.get('info_rows', []):
            self._write_grouped_info_row(ws, current_row, info_values, total_columns, info_font, left_alignment, thin_border)
            current_row += 1

        ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=total_columns)
        ws.cell(row=current_row, column=1, value='商品明细')
        ws.cell(row=current_row, column=1).font = Font(size=11, bold=True)
        ws.cell(row=current_row, column=1).alignment = center_alignment
        ws.cell(row=current_row, column=1).fill = section_fill
        for col_idx in range(1, total_columns + 1):
            ws.cell(row=current_row, column=col_idx).border = thin_border
        header_row = current_row + 1

        for col_idx, column in enumerate(columns, 1):
            cell = ws.cell(row=header_row, column=col_idx, value=column['header'])
            cell.fill = header_fill
            cell.font = white_font
            cell.alignment = center_alignment
            cell.border = thin_border

        data_start_row = header_row + 1
        for row_offset, item in enumerate(context['items']):
            row_idx = data_start_row + row_offset
            for col_idx, column in enumerate(columns, 1):
                value = self._resolve_mall_column_value(item, column)
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.border = thin_border
                if column.get('currency') and value not in ('', None):
                    cell.number_format = '¥#,##0.00'
                cell.alignment = center_alignment if column.get('align') == 'center' else wrap_alignment

        total_row = data_start_row + len(context['items'])
        total_label_end = max(1, total_columns - 3)
        ws.merge_cells(start_row=total_row, start_column=1, end_row=total_row, end_column=total_label_end)
        ws.cell(row=total_row, column=1, value=f"金额大写：{context['amount_to_chinese']}")
        ws.cell(row=total_row, column=total_columns - 1, value='总计')
        ws.cell(row=total_row, column=total_columns, value=context['all_sum_price'])
        ws.cell(row=total_row, column=total_columns).number_format = '¥#,##0.00'

        for col_idx in range(1, total_columns + 1):
            cell = ws.cell(row=total_row, column=col_idx)
            cell.fill = section_fill
            cell.font = total_font
            cell.alignment = center_alignment if col_idx in {total_columns - 1, total_columns} else left_alignment
            cell.border = thin_border

        current_row = total_row + 2
        for note in config.get('notes', []):
            ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=total_columns)
            ws.cell(row=current_row, column=1, value=note)
            ws.cell(row=current_row, column=1).font = note_font
            ws.cell(row=current_row, column=1).alignment = left_alignment
            current_row += 1

        ws.freeze_panes = f'A{data_start_row}'

        timestamp = context['create_time'].strftime('%Y%m%d_%H%M%S_%f')
        customer_suffix = self._safe_filename_segment(customer_name)
        customer_suffix = f'_{customer_suffix}' if customer_suffix else ''
        filename_prefix = self._safe_filename_segment(context.get('template_label')) or config['filename_prefix']
        filename = f"{filename_prefix}{customer_suffix}_{timestamp}.xlsx"
        filepath = os.path.join(output_dir, filename)
        wb.save(filepath)
        return filepath

    def export_mall_quote_template(self, results: List[Dict], output_dir: str,
                                   price_adjustment: Dict = None, price_type: str = 'market',
                                   customer_name: str = '') -> str:
        """导出商城风格报价单"""
        return self.export_mall_document_template(
            results,
            output_dir,
            price_adjustment=price_adjustment,
            price_type=price_type,
            customer_name=customer_name,
            template_definition={
                'doc_type': 'quote',
                'template_variant': 'classic',
                'label': '商城报价单（经典）'
            }
        )

    def _build_mall_quote_context(self, results: List[Dict], price_adjustment: Dict = None,
                                  price_type: str = 'market', customer_name: str = '') -> Dict[str, Any]:
        """兼容旧接口：构建商城报价单上下文"""
        return self._build_mall_document_context(
            results,
            price_adjustment=price_adjustment,
            price_type=price_type,
            customer_name=customer_name,
            template_definition={
                'doc_type': 'quote',
                'template_variant': 'classic',
                'label': '商城报价单（经典）'
            }
        )

    def _build_mall_quote_export_config(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """兼容旧接口：构建商城报价导出配置"""
        return self._build_mall_document_export_config(context)

    def _build_mall_quote_template_reference(self) -> Optional[Path]:
        """兼容旧接口：返回商城报价模板路径"""
        return self._get_mall_quote_template_path()

    def _build_mall_quote_sheet(self, wb: Workbook, context: Dict[str, Any]):
        """兼容占位接口，当前由通用商城单据导出函数统一处理。"""
        return wb, context

    def _build_mall_quote_filename(self, customer_name: str, create_time: datetime) -> str:
        """兼容旧接口：构建商城报价导出文件名"""
        timestamp = create_time.strftime('%Y%m%d_%H%M%S')
        customer_suffix = self._safe_filename_segment(customer_name)
        customer_suffix = f'_{customer_suffix}' if customer_suffix else ''
        return f'商城模板报价单{customer_suffix}_{timestamp}.xlsx'

    def _build_mall_quote_total_label(self, context: Dict[str, Any]) -> str:
        """兼容旧接口：构建金额大写标签"""
        return f"金额大写：{context.get('amount_to_chinese', '')}"

    def _build_mall_quote_notes(self, context: Dict[str, Any]) -> List[str]:
        """兼容旧接口：构建说明文本"""
        return ['说明：本报价单由一键报价系统按商城模板规则生成，可继续扩展为订货单、发货单等模板。']

    def _build_mall_quote_headers(self) -> List[str]:
        """兼容旧接口：商城报价列表头"""
        return ['序号', '品牌', '商品名称', '规格', '数量', '单价', '单位', '小计', '备注']

    def _build_mall_quote_doc_title(self) -> str:
        """兼容旧接口：商城报价单标题"""
        return '报价单'

    def _build_mall_quote_filename_prefix(self) -> str:
        """兼容旧接口：商城报价导出文件名前缀"""
        return '商城模板报价单'

    def _build_mall_quote_sheet_title(self) -> str:
        """兼容旧接口：商城报价工作表名称"""
        return '报价单'

    def _build_mall_quote_note_text(self) -> str:
        """兼容旧接口：商城报价备注"""
        return '说明：本报价单由一键报价系统按商城模板规则生成，可继续扩展为订货单、发货单等模板。'

    def _build_mall_quote_info_rows(self, context: Dict[str, Any]) -> List[List[str]]:
        """兼容旧接口：商城报价信息行"""
        return [
            [f"报价单号：{context['document_no']}", f"报价时间：{context['create_time_display']}", f"报价员：{context['creater_name']}"],
            [f"客户名称：{context['customer_name']}", '单据类型：商城模板报价单', f"参考模板：{context['template_reference']}"]
        ]

    def _build_mall_quote_total_amount(self, context: Dict[str, Any]) -> float:
        """兼容旧接口：返回报价总金额"""
        return context.get('all_sum_price', 0.0)

    def _build_mall_quote_items_count(self, context: Dict[str, Any]) -> int:
        """兼容旧接口：返回报价明细数量"""
        return len(context.get('items', []))

    def _build_mall_quote_reference_name(self, context: Dict[str, Any]) -> str:
        """兼容旧接口：返回参考模板名"""
        return context.get('template_reference', '')

    def _build_mall_quote_customer_name(self, context: Dict[str, Any]) -> str:
        """兼容旧接口：返回客户名"""
        return context.get('customer_name', '')

    def _build_mall_quote_document_no(self, context: Dict[str, Any]) -> str:
        """兼容旧接口：返回单据号"""
        return context.get('document_no', '')

    def _build_mall_quote_create_time_display(self, context: Dict[str, Any]) -> str:
        """兼容旧接口：返回创建时间文本"""
        return context.get('create_time_display', '')

    def _build_mall_quote_creator_name(self, context: Dict[str, Any]) -> str:
        """兼容旧接口：返回制单人"""
        return context.get('creater_name', '')

    def _build_mall_quote_amount_to_chinese(self, context: Dict[str, Any]) -> str:
        """兼容旧接口：返回金额大写"""
        return context.get('amount_to_chinese', '')

    def _build_mall_quote_output_path(self, output_dir: str, filename: str) -> str:
        """兼容旧接口：构建输出路径"""
        return os.path.join(output_dir, filename)

    def _build_mall_quote_output_dir(self, output_dir: str) -> str:
        """兼容旧接口：确保输出目录存在"""
        os.makedirs(output_dir, exist_ok=True)
        return output_dir

    def _build_mall_quote_total_row_label(self, context: Dict[str, Any]) -> str:
        """兼容旧接口：总计标签"""
        return '总计'

    def _build_mall_quote_section_title(self) -> str:
        """兼容旧接口：明细区标题"""
        return '商品明细'

    def _build_mall_quote_variant_label(self) -> str:
        """兼容旧接口：模板版本标签"""
        return '经典版'

    def _build_mall_quote_doc_type_label(self) -> str:
        """兼容旧接口：单据类型标签"""
        return '商城模板报价单'

    def _build_mall_quote_default_template_definition(self) -> Dict[str, Any]:
        """兼容旧接口：默认模板定义"""
        return {'doc_type': 'quote', 'template_variant': 'classic', 'label': '商城报价单（经典）'}

    def import_products(self, file) -> List[Dict]:
        """
        导入商品库

        Args:
            file: 上传的文件对象

        Returns:
            商品列表
        """
        try:
            df = pd.read_excel(file, engine='xlrd' if file.filename.endswith('.xls') else 'openpyxl')
        except:
            df = pd.read_excel(file)

        products = []

        for _, row in df.iterrows():
            product = {
                'code': row.get('* 商品编码', ''),
                'name': row.get('* 商品名称', ''),
                'model': row.get('* 型号', ''),
                'category': row.get('* 商品类别', ''),
                'unit': row.get('* 单位', ''),
                'market_price': row.get('* 市场价', 0),
                'cost_price': row.get('成本价', 0),
                'brand': row.get('商品品牌', ''),
                'supplier': row.get('所属供应商', ''),
                'status': row.get('状态', ''),
                'intro': row.get('商品介绍', ''),
            }

            if product['name'] and str(product['name']).strip():
                products.append(product)

        return products

    def export_quote_with_dropdown(self, results: List[Dict], output_dir: str,
                                    customer_name: str = '', max_candidates: int = 20) -> str:
        """
        导出带下拉框的报价单（供客服人工选择）

        Args:
            results: 匹配结果列表
            output_dir: 输出目录
            customer_name: 客户名称
            max_candidates: 每个产品最多显示的候选商品数

        Returns:
            输出文件路径
        """
        # 创建工作簿
        wb = Workbook()
        ws_main = wb.active
        ws_main.title = '报价单'

        # 表头
        headers = ['序号', '需求产品', '规格要求', '颜色/备注', '需求数量', '单位',
                   '选择商品', '商品编码', '单价', '总价', '品牌', '供应商']

        for col, header in enumerate(headers, 1):
            cell = ws_main.cell(row=1, column=col, value=header)
            cell.fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
            cell.font = Font(bold=True, color='FFFFFF')
            cell.alignment = Alignment(horizontal='center', vertical='center')

        # 创建候选商品工作表
        ws_candidates = wb.create_sheet('候选商品')

        # 写入数据
        for row_idx, result in enumerate(results, 2):
            query_item = result.get('query_item', {})
            # 使用matches字段（不是candidates）
            matches = result.get('matches', [])[:max_candidates]

            # 基本信息
            ws_main.cell(row=row_idx, column=1, value=row_idx - 1)  # 序号
            ws_main.cell(row=row_idx, column=2, value=query_item.get('name', ''))  # 需求产品
            ws_main.cell(row=row_idx, column=3, value=query_item.get('spec', ''))  # 规格要求
            ws_main.cell(row=row_idx, column=4, value=query_item.get('color', '') or query_item.get('remark', ''))  # 颜色/备注
            ws_main.cell(row=row_idx, column=5, value=query_item.get('quantity', ''))  # 需求数量
            ws_main.cell(row=row_idx, column=6, value=query_item.get('unit', ''))  # 单位

            # 选择商品列（下拉框）
            # 在候选商品工作表中写入该行的候选商品列表
            candidate_names = ['--请选择--']
            for c_idx, match in enumerate(matches):
                product = match.get('product', {})
                name = product.get('name', '')
                code = product.get('code', '')
                price = product.get('market_price', 0) or 0
                brand = product.get('brand', '')
                supplier = product.get('supplier', '')
                score = match.get('score', 0)

                # 显示格式: 商品名称 (编码) - 价格元
                display_name = f"{name} [{code}] ¥{price}"
                candidate_names.append(display_name)

                # 在候选商品工作表中写入详细信息（用于VLOOKUP）
                cand_row = (row_idx - 2) * max_candidates + c_idx + 2
                ws_candidates.cell(row=cand_row, column=1, value=row_idx - 1)  # 对应主表行号
                ws_candidates.cell(row=cand_row, column=2, value=display_name)  # 显示名称
                ws_candidates.cell(row=cand_row, column=3, value=code)  # 商品编码
                ws_candidates.cell(row=cand_row, column=4, value=price)  # 单价
                ws_candidates.cell(row=cand_row, column=5, value=brand)  # 品牌
                ws_candidates.cell(row=cand_row, column=6, value=supplier)  # 供应商
                ws_candidates.cell(row=cand_row, column=7, value=score)  # 匹配分数

            # 创建下拉框
            if len(candidate_names) > 1:
                # 使用逗号分隔的列表创建下拉框
                dropdown_list = ','.join(candidate_names[:50])  # Excel限制最多255字符
                if len(dropdown_list) > 255:
                    # 如果太长，使用引用方式
                    start_row = (row_idx - 2) * max_candidates + 2
                    end_row = start_row + len(candidate_names) - 2
                    formula = f"候选商品!$B${start_row}:$B${end_row}"
                    dv = DataValidation(type="list", formula1=formula, allow_blank=True)
                else:
                    dv = DataValidation(type="list", formula1=f'"{dropdown_list}"', allow_blank=True)

                dv.error = '请从列表中选择商品'
                dv.errorTitle = '无效输入'
                dv.prompt = '请选择匹配的商品'
                dv.promptTitle = '选择商品'
                ws_main.add_data_validation(dv)
                dv.add(ws_main.cell(row=row_idx, column=7))  # 选择商品列

            ws_main.cell(row=row_idx, column=7, value='--请选择--')

            # 商品编码列 - 使用公式根据选择自动填充
            ws_main.cell(row=row_idx, column=8, value='')

            # 单价列
            ws_main.cell(row=row_idx, column=9, value='')

            # 总价列 - 公式（数量在E列，单价在I列）
            ws_main.cell(row=row_idx, column=10, value=f'=IF(I{row_idx}="","",E{row_idx}*I{row_idx})')

            # 品牌、供应商
            ws_main.cell(row=row_idx, column=11, value='')
            ws_main.cell(row=row_idx, column=12, value='')

        # 设置列宽
        column_widths = [6, 20, 25, 15, 10, 8, 40, 15, 10, 12, 12, 15]
        for i, width in enumerate(column_widths, 1):
            ws_main.column_dimensions[get_column_letter(i)].width = width

        # 隐藏候选商品工作表
        ws_candidates.sheet_state = 'hidden'

        # 设置候选商品工作表表头
        cand_headers = ['主表行号', '显示名称', '商品编码', '单价', '品牌', '供应商', '匹配分数']
        for col, header in enumerate(cand_headers, 1):
            ws_candidates.cell(row=1, column=col, value=header)

        # 添加说明行
        note_row = len(results) + 3
        ws_main.cell(row=note_row, column=1, value='说明：')
        ws_main.cell(row=note_row + 1, column=1, value='1. 点击"选择商品"列的下拉框，可以看到匹配的候选商品')
        ws_main.cell(row=note_row + 2, column=1, value='2. 选择后请手动填写商品编码、单价等信息')
        ws_main.cell(row=note_row + 3, column=1, value='3. 总价会自动计算')

        # 生成文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        customer_suffix = f'_{customer_name}' if customer_name else ''
        filename = f'待选报价单{customer_suffix}_{timestamp}.xlsx'
        filepath = os.path.join(output_dir, filename)

        # 保存
        wb.save(filepath)

        return filepath